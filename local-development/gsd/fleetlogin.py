"""Log in to a target cluster as the fleet account, and log out again — the session of #283.

WHAT THIS IS. `oc login -u … -p …` is the OAuth challenging-client flow that `gsd/auditlog.py`
already documents as the `cli` login kind: one GET on the target's authorization endpoint with HTTP
basic auth, answered by a 302 whose `Location` FRAGMENT carries the access token and its lifetime.
This module performs that request as the fleet account (SPEC_S3 §3.1), hands the caller a session —
the token, the account it belongs to, and the ABSOLUTE INSTANT it expires — and revokes the token
when the caller is done, whatever happened in between. Nothing here stores anything, writes a Secret
or schedules anything: the lookup that stores is #284, the lifecycle is #285.

MEASURED ON THE REFERENCE CLUSTER, 2026-09-21, with the htpasswd `developer` account (the fleet
account is never logged in with to test anything — SPEC_S4a, orchestrator's notes):

  GET /.well-known/oauth-authorization-server          -> authorization_endpoint =
                                                           https://oauth-openshift.apps-crc.testing/oauth/authorize
  GET <that>?client_id=openshift-challenging-client&response_type=token   basic auth, X-CSRF-Token: 1
  -> 302, empty body, Location: …/oauth/token/implicit#access_token=sha256~…&expires_in=31536000&…
  DELETE /apis/oauth.openshift.io/v1/useroauthaccesstokens/<name>       as the token's own user -> 200

THREE THINGS THE FLOW DICTATES:

1. THE OAUTH HOST IS DISCOVERED, NEVER DERIVED. `oauth-openshift.apps-crc.testing` serves an API at
   `api.crc.testing:6443`: no string transformation between the two is right in general, and the
   API server publishes the answer, unauthenticated, at the well-known path.
2. THE TOKEN IS READ OFF THE `Location` HEADER. A fragment is never sent to a server and is never in
   a body, so the client must not follow the redirect — following it loses the token.
3. THE LIFETIME IS THE TARGET'S. `expires_in` is 31536000 s (a year) on the reference cluster and
   86400 s (a day) by OpenShift's default; an estate may set an hour. The session records
   `obtained_at + expires_in` as an instant — never "daily", and never an age (the operator's
   ruling: server-side text carries instants).

THE RETRY POLICY IS THE HIGH-BLAST-RADIUS PART, and it ships with the first code that can log in.
The line is drawn at THE PASSWORD BEING ON THE WIRE, not at the kind of answer:

  discovery (no password is sent): any failure
      -> bounded exponential backoff to `RETRY_POLICY.attempts`, then give up OUT LOUD
  the authorize GET failed BEFORE its bytes were written — the socket never opened or the TLS
  handshake failed (httpx.ConnectError, httpx.ConnectTimeout)
      -> the same backoff: the target cannot have bound
  the authorize GET was written and ANYTHING came back — a 401, a 5xx, a 200, a 302 without a
  token, a read timeout, a dropped connection
      -> TERMINAL. One `fleet-login-refused` line for a 401 with a Basic challenge, one
         `fleet-login-failed … not retried` line for everything else. Stop.

WHY EVERY ANSWER IS TERMINAL (review of #289; verified against upstream by the business owner): the
oauth-server's LDAP authenticator answers 401 only for LDAP result codes 48 and 49
(pkg/authenticator/password/ldappassword/ldap.go) and EVERY other directory result with 500
(pkg/osinserver/defaults.go, HandleError) — including code 19, `Exceeded password retry limit`,
which is what a directory that has ALREADY LOCKED the account says. A "5xx is transient" rule
therefore retries hardest exactly when the account is locked. A 504 means the upstream took too
long having RECEIVED the request; a 502 that it answered malformed having received it; a read
timeout that the request was written. The asymmetry decides it: a wrong retry is an estate-wide
outage against the account the target authenticates EVERY user with; a missed retry is one delayed
login that #285's daily ping picks up. Suspending the credential across clusters needs a
coordinator and is #285's; the half that needs none is here.

A MINTED TOKEN IS NEVER ABANDONED — stated precisely, because a remote delete can always fail:
from the moment the 302 is in hand, nothing leaves the login without either handing the token to
the caller inside a session or ATTEMPTING ITS REVOCATION EXACTLY ONCE, and a failed revocation is
SURFACED — a `fleet-logout-failed` line, `FleetLogin.revoked` False — never swallowed and never
reported as success. Whatever raises, including what was not predicted; and cleanup never replaces
the exception it is cleaning up after. THE GUARD IS ANCHORED ON THE RESPONSE, NOT ON A BINDING:
on any failure it re-reads the token off the response's own header (`_token_in`, pure and total),
so there is no line between "the token exists in this process" and "an exception here revokes
it" — three refactors moved "the moment the token is bound" and each reopened the window (review
of #289, three passes). The token is read off the header WITHOUT validating the rest of the URL (a
hostile `Location` must not stand between the mint and the name of what was minted), and the
lifetime the target states is bounded at int32 (MAX_EXPIRES_IN) because it is remote-controlled
and the instant arithmetic is not. `FleetLogin.revoked` is what the target answered, recorded from
EVERY revoke site.

REDACTION NEVER TOUCHES WHAT THE CODE DERIVES MEANING FROM (the third pass, correcting the
second): a classification input — the 401 challenge, a transport message's OpenSSL phrases — is
classified RAW and only the quoted copy is scrubbed; a structured value the operator acts on — the
issuer URL, the endpoint's host — is never substring-redacted, and userinfo is stripped from it
structurally; length-agnostic redaction is kept only for genuinely free remote text (bodies,
challenge values, error strings), where mangling costs a less readable quote and nothing else. What this cannot cover, and both are why the
answer is terminal rather than retried: a request the target answered after this process stopped
listening (a read timeout), and a 302 whose `Location` httpx itself cannot parse (it builds the
redirect request even with `follow_redirects=False` and raises `RemoteProtocolError`) — either may
have minted a token this process never saw, which is #286's litter.

THE SESSION IS A CONTEXT MANAGER. Every login mints an `OAuthAccessToken` on the target and this
module owns revoking it: `__exit__` deletes it by name after the body ran, after the body raised,
and — inside the login itself — when a token was minted but no session could be built from it.
That is what lets the lookup and the daily ping leave nothing behind by construction.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx

from .clusterconfig.events import event, failure, is_verify_failure, redact
from .config import ClusterConfig, ConfigError
from .kube import AUTH_FAILED, UNREACHABLE, ClusterError, redact_text

log = logging.getLogger(__name__)

#: Where an API server publishes its OAuth server (RFC 8414's well-known path), unauthenticated.
DISCOVERY_PATH = "/.well-known/oauth-authorization-server"
#: The client `oc login` and `curl -u` present; `gsd/auditlog.py` classifies its logins as `cli`.
CHALLENGING_CLIENT = "openshift-challenging-client"
#: The header `oc` sends on the challenging flow; the oauth-server's CSRF check reads it.
CSRF_HEADER = {"X-CSRF-Token": "1"}
#: A user's own tokens. DELETE by name revokes one, authorised by the token itself — `oc logout`.
USER_TOKEN_API = "/apis/oauth.openshift.io/v1/useroauthaccesstokens"
#: A token since OpenShift 4.6 is `sha256~<random>`, and its OAuthAccessToken object is named
#: `sha256~<base64url(sha256(<random>))>` so that the token itself is never an object's name.
TOKEN_PREFIX = "sha256~"
#: The largest lifetime a target can legitimately state: `OAuthClient.accessTokenMaxAgeSeconds` is an
#: int32 in oauth.openshift.io/v1. Anything above it is a remote-controlled value that would overflow
#: the instant arithmetic (review of #289, all three seats): the token is revoked and the answer is
#: terminal.
MAX_EXPIRES_IN = 2**31 - 1
#: The refusal line's outcome. It joins `clusterconfig.FINDING_CODES` — and the tab's sentence for
#: it — in #284, the step that first puts a lookup's findings on the page (SPEC_S1 §S1.2).
LOGIN_REFUSED = "login-refused"
#: The stamp every instant this module reports is written in: `gsd/timeutil.py`'s, fixed-width UTC.
STAMP = "%Y-%m-%dT%H:%M:%SZ"
#: Every event name this module emits — in one place, so the redaction pin can prove it drove each.
EVENTS = ("fleet-login", "fleet-login-failed", "fleet-login-refused", "fleet-logout", "fleet-logout-failed")


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded exponential backoff for the failures that are safe to retry.

    `attempts` is the ceiling the log quotes as `attempt=<n>/<ceiling>`; the wait after the n-th
    failure is `base_seconds × 2^(n−1)`, capped at `max_wait_seconds`. Deterministic — no jitter —
    because the design has one retriever per estate (SPEC_S4 §6, the replica rule), so there is no
    herd to spread, and a stated sequence is one a reader can check against the `retry_in=` lines.
    """

    attempts: int = 5
    base_seconds: float = 1.0
    max_wait_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError(f"a retry policy needs at least one attempt, not {self.attempts}")

    def wait_after(self, failed_attempt: int) -> float:
        return min(self.base_seconds * (2 ** (failed_attempt - 1)), self.max_wait_seconds)


#: The stated ceiling: five attempts, waiting 1, 2, 4 and 8 seconds between them — 15 s of backoff
#: plus up to five request timeouts, so a target that is down costs about a minute and a half before
#: the loop gives up out loud. Nothing locks on any of these: a refusal never reaches this loop.
RETRY_POLICY = RetryPolicy()


class LoginError(ClusterError):
    """A login that produced no session, typed for the caller's next decision.

    `outcome` is `gsd.kube`'s word — `auth_failed` for a refusal, `unreachable` for everything
    else; `phase` is where it failed, from #245's closed set; `retryable` is what the policy
    consulted — False for a refusal, for any other 401, for a CA bundle this pod cannot load, and
    for an answer this module refuses to retry into; `attempts` is how many logins were tried.
    The message never carries the password: every raise site scrubs it first.
    """

    def __init__(self, outcome: str, message: str, *, phase: str, retryable: bool):
        super().__init__(outcome, message)
        self.phase = phase
        self.retryable = retryable
        self.attempts = 0


@dataclass(frozen=True)
class _RevokeAnswer:
    """What the target said to a DELETE, decided on the wire before any line is written about it."""

    gone: bool
    """True only when the target answered 200 (revoked) or 404 (already gone)."""
    name: str | None
    """The object's name as the wire used it, or None when the wire was never reached."""
    word: str
    """revoked | already-gone | unauthenticated | refused | unanswered — the line's `outcome=` word."""
    phase: str
    outcome: str
    detail: str | None


@dataclass(frozen=True)
class FleetSession:
    """One login as the fleet account: the token, whose it is, and when it dies."""

    cluster: str
    account: str
    token: str = field(repr=False, compare=False)
    obtained_at: datetime
    """UTC, read BEFORE the login request left this process."""
    expires_in: int
    """Seconds, the target's own figure exactly as the fragment carried it."""
    issuer: str
    """The OAuth server the token came from, as the target's discovery document named it."""
    attempts: int
    """How many logins it took; 1 when the first succeeded."""

    def __post_init__(self) -> None:
        # The instants this session reports carry a `Z`, so what it holds must BE UTC: an injected
        # clock is normalised at the read (`_as_utc`) and refused here if it slipped past naive
        # (review of #289, Codex) — a naive datetime cannot be normalised without guessing its zone.
        if self.obtained_at.utcoffset() is None:
            raise ValueError("FleetSession.obtained_at must be an aware datetime")

    @property
    def expires_at(self) -> datetime:
        """The absolute instant the session dies: `obtained_at + expires_in`. `obtained_at` is the
        clock before the request left, so this errs EARLY — the dashboard may believe a session
        died a round-trip before it did, never after."""
        return self.obtained_at + timedelta(seconds=self.expires_in)

    @property
    def expires_at_iso(self) -> str:
        return self.expires_at.astimezone(UTC).strftime(STAMP)

    @property
    def token_name(self) -> str:
        return token_object_name(self.token)


def token_object_name(token: str) -> str:
    """The name of the OAuthAccessToken object a token corresponds to.

    Measured on the reference cluster: `sha256~` + base64url(sha256(the part after the prefix)),
    unpadded, is exactly the name `oc get oauthaccesstokens` lists for a token minted by this flow.
    A token WITHOUT the prefix (a cluster older than 4.6) is its own object's name — which is why
    the name is never logged unprefixed and every line carries the token in `secrets=`.
    """
    if not token.startswith(TOKEN_PREFIX):
        return token
    digest = hashlib.sha256(token[len(TOKEN_PREFIX):].encode()).digest()
    return TOKEN_PREFIX + base64.urlsafe_b64encode(digest).decode().rstrip("=")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _describe(exc: BaseException) -> str:
    return type(exc).__name__


def _text_of(exc: BaseException) -> str:
    """`str(exc)`, and never the reason cleanup raises: an exception whose `__str__` raises would
    otherwise replace the exception being cleaned up after (final pass, R5-3)."""
    try:
        return str(exc)
    except BaseException:  # noqa: BLE001 - the description is all that is left to say
        return "<unprintable>"


def _without_userinfo(url: str) -> str | None:
    """A URL rebuilt from its parts without any userinfo — `scheme://host[:port]/path` — or None
    when it is not an https URL with a host. STRUCTURAL, not a substring redaction (third pass: the
    round-2 scrub turned `…apps.example.com` into `…<redacted>s.example.com` for a password of
    `app`); a host that happens to contain the password is the operator's host and survives."""
    try:
        parts = urlsplit(url)
        hostname, port = parts.hostname, parts.port     # `.port` raises on a port that is not a number
    except ValueError:
        return None
    if parts.scheme != "https" or not hostname:
        # `https://:bad/x` has no host and `https://host:bad/x` no usable port: both would rebuild
        # into a malformed authority, so both fall back to the endpoint's host (final pass, R5-4).
        return None
    del port
    return f"{parts.scheme}://{parts.netloc.rpartition('@')[2]}{parts.path}"


def _as_utc(moment: datetime) -> datetime:
    """An injected clock's reading, in UTC. Aware in any zone is converted; naive is refused, because
    a `Z`-suffixed instant built from a naive reading would claim a zone it does not have."""
    if moment.utcoffset() is None:
        raise ValueError("the clock must return an aware datetime")
    return moment.astimezone(UTC)


class FleetLogin:
    """`with FleetLogin(cluster, username, password) as session:` — log in on enter, log out on exit.

    The password is taken as a value and held only for the login. It is not a field of
    `ClusterConfig`, so `poller._credentials` never sees it (SPEC_S3 §3.1 rule 4): every line this
    class emits hands it — and the token, once there is one — to the emit helper as `secrets=`, and
    every message that can reach a caller is scrubbed of it first.

    `timeout` is the per-request budget the poller gives `ClusterClient` (`requestTimeoutSeconds`);
    `policy`, `sleep` and `clock` are the loop's knobs, injectable so a test can drive the whole
    ceiling without waiting fifteen seconds or trusting the wall clock. One instance is one session:
    entering it twice is refused.
    """

    def __init__(self, cluster: ClusterConfig, username: str, password: str, *,
                 timeout: float = 15.0, policy: RetryPolicy = RETRY_POLICY,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], datetime] = _utcnow):
        self.cluster = cluster
        self.username = username
        self._password = password
        self._timeout = timeout
        self._policy = policy
        self._sleep = sleep
        self._clock = clock
        self._client: httpx.Client | None = None
        self._entered = False
        self.session: FleetSession | None = None
        #: Whether the session's token was revoked on exit: None until then, True only when the
        #: target answered the DELETE 200 or 404, False for every surfaced failure (review of #289,
        #: confirmation pass: a 500 must never be reported to the caller as revoked).
        self.revoked: bool | None = None

    # ── the context manager ──────────────────────────────────────────────────────────────────

    def __enter__(self) -> FleetSession:
        if self._entered:
            raise RuntimeError(f"FleetLogin for {self.cluster.name!r} is one session; make a new one")
        self._entered = True
        try:
            self._client = self._build_client()
        except LoginError as exc:
            self._log_stop(exc)
            raise
        try:
            self.session = self._login()
        except BaseException:
            self._close()
            raise
        return self.session

    def __exit__(self, exc_type, exc, tb) -> bool:
        try:
            if self.session is not None:
                self._revoke(self.session.token)
        finally:
            self._close()
        return False

    def _close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    # ── the client ───────────────────────────────────────────────────────────────────────────

    def _build_client(self) -> httpx.Client:
        """One client for discovery, the login and the logout, verifying the target exactly as the
        poller does — `ClusterConfig.verify()` is the one TLS decision (SPEC_S3 §6) — and NEVER
        following a redirect, because the token is in the redirect."""
        try:
            verify = self.cluster.verify()
        except ConfigError as exc:
            # A CA bundle this pod cannot load is local, not the target's doing, and no retry
            # changes it — the same classification `ClusterClient._client` makes.
            raise LoginError(UNREACHABLE, str(exc), phase="tls", retryable=False) from exc
        return httpx.Client(base_url=self.cluster.api_url, verify=verify, timeout=self._timeout,
                            follow_redirects=False)

    # ── the login, under the policy ──────────────────────────────────────────────────────────

    def _login(self) -> FleetSession:
        policy = self._policy
        attempt = 0
        while True:
            attempt += 1
            obtained_at = _as_utc(self._clock())
            try:
                issuer, endpoint = self._discover()
                response = self._authorize(endpoint)
            except LoginError as exc:
                exc.attempts = attempt
                if not exc.retryable:
                    self._log_stop(exc)
                    raise
                if attempt >= policy.attempts:
                    self._log_retry(exc, attempt, gave_up=True)
                    raise
                wait = policy.wait_after(attempt)
                self._log_retry(exc, attempt, retry_in=wait)
                self._sleep(wait)
                continue
            # FROM HERE THE TARGET MAY HAVE MINTED A TOKEN: the response is in hand, and this guard
            # holds until the session is returned. THE CLEANUP DEPENDS ON NO LATER BINDING (third
            # pass, Codex: an interruption after the token was bound inside `_token_from` still
            # abandoned it — the third time "the moment the token is bound" moved with a refactor).
            # On any exception the guard re-reads the token off the RESPONSE ITSELF (`_token_in`,
            # pure and total), so there is no line between "the token exists in this process" and
            # "an exception here revokes it": the response has carried it since the request returned.
            # Revocation is attempted exactly once: nothing inside this block revokes.
            try:
                token, fragment = self._token_from(response, endpoint)
                expires_in = self._expiry_from(fragment, endpoint)
                session = FleetSession(cluster=self.cluster.name, account=self.username, token=token,
                                       obtained_at=obtained_at, expires_in=expires_in, issuer=issuer,
                                       attempts=attempt)
                event(log, logging.INFO, "fleet-login", **self._fields(), oauth=issuer,
                      expires_at=session.expires_at_iso,
                      attempt=f"{attempt}/{policy.attempts}" if attempt > 1 else None,
                      secrets=(self._password, token))
            except BaseException as problem:
                minted = self._token_in(response)
                if minted is not None:
                    self._revoke(minted)
                if isinstance(problem, LoginError):
                    problem.attempts = attempt
                    self._log_stop(problem)
                raise
            return session

    def _discover(self) -> tuple[str, str]:
        """(issuer, authorization_endpoint) from the target's well-known document. Unauthenticated,
        so a failure here has bound nothing — it is retried like any other transport failure."""
        try:
            response = self._client.get(DISCOVERY_PATH, headers={"Accept": "application/json"})
        except httpx.HTTPError as exc:
            raise self._transport_error(exc) from exc
        if response.status_code != 200:
            raise LoginError(UNREACHABLE, f"HTTP {response.status_code} on {DISCOVERY_PATH}: "
                             f"{self._scrub(response.text)[:200]}", phase="connect", retryable=True)
        try:
            document = response.json()
        except ValueError as exc:
            raise LoginError(UNREACHABLE, f"non-JSON response from {DISCOVERY_PATH}: {exc}",
                             phase="connect", retryable=True) from exc
        endpoint = document.get("authorization_endpoint") if isinstance(document, dict) else None
        try:
            parts = urlsplit(endpoint) if isinstance(endpoint, str) else None
        except ValueError as exc:
            # `urlsplit` refuses some hostile strings (an unclosed IPv6 literal) with a ValueError
            # whose text must not reach the caller unscrubbed (confirmation pass, Codex).
            raise LoginError(UNREACHABLE, f"{DISCOVERY_PATH} names an authorization_endpoint that does "
                             f"not parse: {self._scrub(str(exc))[:200]}", phase="connect", retryable=False) from exc
        if parts is None or parts.scheme != "https" or not parts.netloc:
            # The password travels on this URL. Anything but https is refused and never retried
            # into: a document naming a plain-http endpoint is a fact about the target, not weather.
            raise LoginError(UNREACHABLE, f"{DISCOVERY_PATH} names no https authorization_endpoint "
                             f"(got {self._scrub(str(endpoint))[:200]!r})", phase="connect", retryable=False)
        if parts.username is not None or parts.password is not None:
            # Userinfo on the endpoint is a remote-controlled secret-shaped string that would ride into
            # every message naming the host (review of #289): refused, and never quoted.
            raise LoginError(UNREACHABLE, f"{DISCOVERY_PATH} names an authorization_endpoint carrying "
                             f"userinfo; refused", phase="connect", retryable=False)
        # The issuer is a remote field that reaches the caller on the session and the log as
        # `oauth=` — and it is a URL the operator acts on, so userinfo is stripped STRUCTURALLY
        # rather than by redaction (third pass; the round-2 scrub mangled a legitimate host).
        issuer = document.get("issuer")
        rebuilt = _without_userinfo(issuer) if isinstance(issuer, str) and issuer else None
        return rebuilt or f"https://{parts.netloc}", endpoint

    def _authorize(self, endpoint: str) -> httpx.Response:
        """The challenging-client request. Returns the response; reading the token off it is
        `_token_from`, kept apart so that everything after the response is in hand runs under the
        never-abandoned guard in `_login` — which re-reads the token off this response on failure.

        ONCE THE GET CARRYING THE PASSWORD IS ISSUED, EVERY OUTCOME IS TERMINAL (the module
        docstring says why). The one retryable failure here is one provably before the password
        bytes were written: the socket never opened, or the TLS handshake failed.
        """
        try:
            response = self._client.get(endpoint, params={"client_id": CHALLENGING_CLIENT, "response_type": "token"},
                                        headers=CSRF_HEADER, auth=(self.username, self._password))
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            # Provably before the password bytes were written: the target cannot have bound.
            raise self._transport_error(exc) from exc
        except httpx.HTTPError as exc:
            # The request may have been written and the target may have bound — a read timeout, a
            # dropped connection, a non-HTTP answer: terminal.
            raise self._transport_error(exc, retryable=False) from exc
        else:
            # Returned from inside the protected region (final pass, R5-2): the response must not
            # exist in an instruction window outside it. What remains is the store into `_login`'s
            # local after this call returns — one bytecode, and inherent to any call boundary.
            return response

    @staticmethod
    def _fragments_of(response: httpx.Response) -> list[dict[str, list[str]]]:
        """Every fragment a 302 could carry, parsed on its own — the rest of each URL is NEVER
        validated, because a hostile `Location` (an unclosed IPv6 literal makes `urlsplit` raise)
        must not stand between the mint and the name of what was minted (confirmation pass).

        EVERY `Location` VALUE, AND EVERY `#`-SEGMENT OF EACH (final pass, R5-1, measured): httpx
        keeps repeated headers apart in `get_list` but COMMA-JOINS them in `get`, so a first-`#`
        split of the joined string never saw a token in the second header — a minted token the
        guard could not name. A proxy that joined the duplicates itself hands ONE value holding two
        URLs, which `get_list` alone would also miss; splitting each value on every `#` covers both,
        and a fragment cannot legitimately contain a `#`. Total: it cannot raise."""
        return [parse_qs(segment)
                for value in response.headers.get_list("location")
                for segment in value.split("#")[1:]]

    @classmethod
    def _fragment_of(cls, response: httpx.Response) -> dict[str, list[str]]:
        """THE fragment: the first that carries an `access_token`, else the first there is, else
        empty. The session path (`_token_from`) and the guard (`_token_in`) both read this one, so
        they cannot disagree about which token exists — a divergence there would be worse than
        either bug."""
        fragments = cls._fragments_of(response)
        for fragment in fragments:
            if (fragment.get("access_token") or [""])[0]:
                return fragment
        return fragments[0] if fragments else {}

    @classmethod
    def _token_in(cls, response: httpx.Response) -> str | None:
        """The token a response minted, or None — what the never-abandoned guard re-reads on
        failure. Pure and total, and it depends on nothing bound later than the response."""
        if response.status_code != 302:
            return None
        return (cls._fragment_of(response).get("access_token") or [None])[0] or None

    def _token_from(self, response: httpx.Response, endpoint: str) -> tuple[str, dict[str, list[str]]]:
        """The token and the whole fragment off a 302, or the typed stop for every other answer."""
        host = urlsplit(endpoint).netloc   # structured, and `_discover` refused userinfo: never scrubbed
        if response.status_code == 401:
            # THE REFUSAL, and the one answer that is never retried. Measured (SPEC_S4 §6): a wrong
            # password is a bare 401 with `Www-Authenticate: Basic realm="openshift"` and an empty
            # body — there are no server's words to quote beyond that, and the same 401 answers a
            # username the directory cannot find. A 401 WITHOUT the Basic challenge did not
            # necessarily evaluate the password, so it is not recorded as a refusal; it is not
            # retried either, because retrying a 401 whose cause cannot be read is the lockout walk.
            # DECIDE ON THE RAW CHALLENGE, THEN SCRUB THE COPY THAT IS QUOTED (confirmation pass,
            # Codex): a password that is literally `Basic` redacted the challenge before it was
            # classified, and a genuine refusal came out as `unreachable`.
            raw_challenge = response.headers.get("www-authenticate", "")
            is_basic = raw_challenge.strip().lower().startswith("basic")
            challenge = self._scrub(raw_challenge)[:200]
            said = (f"401 Unauthorized from {host}; Www-Authenticate: {challenge or '<absent>'}; "
                    f"body: {self._scrub(response.text)[:200] or '<empty>'}")
            if is_basic:
                raise LoginError(AUTH_FAILED, said, phase="credential", retryable=False)
            raise LoginError(UNREACHABLE, f"{said} — no Basic challenge, so this is a client or server "
                             f"fault rather than a refusal; not retried", phase="credential", retryable=False)
        if response.status_code != 302:
            # The password was on the wire and the target answered: terminal, whatever the status —
            # a 500 is what the oauth-server says for every directory result but 48/49, a locked
            # account's code 19 included.
            raise LoginError(UNREACHABLE, f"HTTP {response.status_code} on {host}/oauth/authorize: "
                             f"{self._scrub(response.text)[:200]}; not retried — the password was sent",
                             phase="credential", retryable=False)
        fragment = self._fragment_of(response)
        token = (fragment.get("access_token") or [""])[0]
        if not token:
            # The bind happened and the grant failed after it: terminal for the same reason.
            error = (fragment.get("error") or ["<none>"])[0]
            raise LoginError(UNREACHABLE, f"302 from {host} carried no access_token in its Location fragment "
                             f"(error={self._scrub(error)[:100]}, keys={self._scrub(','.join(sorted(fragment)))[:100]}); "
                             f"not retried — the password was sent", phase="credential", retryable=False)
        return token, fragment

    def _expiry_from(self, fragment: dict[str, list[str]], endpoint: str) -> int:
        """`expires_in` as the target stated it, bounded. Runs under the never-abandoned guard: a
        token WAS minted, so the guard attempts its revocation once and does not retry into a
        second one — the fragment's shape is a fact about the target."""
        host = urlsplit(endpoint).netloc
        raw_expiry = (fragment.get("expires_in") or [None])[0]
        try:
            expires_in = int(raw_expiry) if raw_expiry is not None else 0
        except ValueError:
            expires_in = 0
        if not 0 < expires_in <= MAX_EXPIRES_IN:
            raise LoginError(UNREACHABLE, f"302 from {host} carried a token without a usable expires_in "
                             f"(got {self._scrub(str(raw_expiry))[:100]!r}; the bound is 1..{MAX_EXPIRES_IN}); "
                             f"its revocation was attempted once — the fleet-logout line says whether it "
                             f"succeeded", phase="credential", retryable=False)
        return expires_in

    # ── the logout ───────────────────────────────────────────────────────────────────────────

    def _delete_token(self, token: str) -> _RevokeAnswer:
        """THE WIRE ONLY — `oc logout`: DELETE the OAuthAccessToken by name, authorised by the token
        itself — answered as a value, before any line is written about it. `gone` is True only when
        the target said so: 200, or 404 (already gone). ONLY a 404 means gone: a 401 says the DELETE
        was not authenticated and nothing about the object (review of #289, Codex). A transport
        failure is an answer here, never a raise.

        The object is gone the moment the DELETE answers 200. The token itself may go on authenticating
        from the API server's token cache for about two minutes (121 s measured on the reference
        cluster) — a fact for #285's "a 401 means re-authenticate" rule, not litter: nothing on the
        target names it any more, and `oc get oauthaccesstokens` shows it gone at once."""
        name = token_object_name(token)   # derived ONCE, here, where the wire needs it (final pass, R5-3)
        try:
            response = self._client.delete(f"{USER_TOKEN_API}/{name}",
                                           headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
        except httpx.HTTPError as exc:
            problem = self._transport_error(exc, token)
            return _RevokeAnswer(False, name, "unanswered", problem.phase, UNREACHABLE, problem.message)
        if response.status_code == 200:
            return _RevokeAnswer(True, name, "revoked", "poll", "revoked", None)
        if response.status_code == 404:
            return _RevokeAnswer(True, name, "already-gone", "poll", "already-gone", None)
        body = self._scrub(response.text, token)[:200] or "<empty body>"
        if response.status_code == 401:
            return _RevokeAnswer(False, name, "unauthenticated", "credential", AUTH_FAILED,
                                 f"401 Unauthorized on DELETE {USER_TOKEN_API}/<name>: the token did not authorise "
                                 f"its own revoke, so the object may still exist — {body}")
        return _RevokeAnswer(False, name, "refused", "poll", UNREACHABLE,
                             f"HTTP {response.status_code} on DELETE {USER_TOKEN_API}/<name>: revoke refused — {body}")

    def _revoke(self, token: str) -> bool:
        """The ONE boundary every revoke site goes through — the exit and the login's guard alike.

        Three things, in this order, and the order is the point (third pass, Codex): the wire
        answers; `revoked` records what the TARGET said, from every site, so the caller (#284, #285)
        reads the truth about what was left behind; and only then is the line written — a line that
        fails to write after a 200 is not a failed revoke, and is said as what it is. Never raises:
        cleanup never replaces the exception it is cleaning up after (confirmation pass), so a fault
        of this process on the wire path is surfaced as a `fleet-logout-failed` line and answered
        False, and a fault while writing the line falls back to the stdlib logger, which cannot raise.
        """
        # NOTHING IS COMPUTED BEFORE THE WIRE THAT THE WIRE DOES NOT NEED (final pass, R5-3): the
        # name is derived once, inside `_delete_token`, and comes back on the answer for the line.
        try:
            answer = self._delete_token(token)
        except BaseException as exc:  # noqa: BLE001 - the wire never raises; this is a fault of this process
            answer = _RevokeAnswer(False, None, "unanswered", "connect", UNREACHABLE,
                                   f"{_describe(exc)}: {self._scrub(_text_of(exc), token)[:200]} — the revoke "
                                   f"itself failed before the target answered")
        self.revoked = answer.gone
        shown = answer.name if answer.name and token.startswith(TOKEN_PREFIX) else None   # unprefixed IS the token
        secrets = (self._password, token)
        try:
            if answer.gone:
                event(log, logging.INFO, "fleet-logout", **self._fields(), token=shown, outcome=answer.word,
                      secrets=secrets)
            else:
                failure(log, "fleet-logout-failed", phase=answer.phase, outcome=answer.outcome, **self._fields(),
                        token=shown,
                        action=("the OAuthAccessToken may still be on the target and nothing here will try "
                                "again: delete it there as cluster-admin (oc delete oauthaccesstoken <token>) "
                                "so it does not become litter"),
                        detail=answer.detail, secrets=secrets)
        except BaseException as exc:  # noqa: BLE001 - the LINE failed, not the revoke; `revoked` already holds the answer
            try:
                log.warning("fleet-logout line could not be written (revoked=%s): %s: %s", answer.gone,
                            _describe(exc), self._scrub(_text_of(exc), token)[:200])
            except BaseException:  # noqa: BLE001, S110 - the last resort: cleanup can never raise (final pass, R5-3)
                pass
        return answer.gone

    # ── the vocabulary ───────────────────────────────────────────────────────────────────────

    def _fields(self) -> dict[str, str]:
        mode = self.cluster.tls_mode
        return {"cluster": self.cluster.name, "account": self.username,
                "tls": "insecure" if mode["insecure"] else mode["ca"]}

    def _scrub(self, text: str, *more: str | None) -> str:
        """Every secret in play out of FREE REMOTE TEXT — a body, a challenge value, an error string,
        a transport message's quoted copy — in both spellings the two helpers know (`gsd.kube`'s
        JSON-escaped forms and the emit helper's) and then, REGARDLESS OF LENGTH, the raw value of
        each (confirmation pass: a three-character password passed both helpers' floors; the floors
        are theirs and stay). Before any truncation, always.

        THREE RULES ON WHERE THIS MAY BE APPLIED (third pass, correcting the round-2 instruction
        "regardless of length, everywhere" — measured: a password of `app` turned the issuer into
        `…<redacted>s.example.com`, and one of `certificate` unclassified a TLS failure into
        `phase=connect`): never on a classification input — decide on the raw value, scrub the
        displayed copy; never on a structured value the operator acts on — the issuer, the endpoint's
        host — where userinfo is stripped structurally instead; only on free text, where mangling
        costs a less readable quote and nothing else."""
        secrets = tuple(v for v in (self._password, *more) if v)
        out = redact(redact_text(text, *secrets), secrets)
        for secret in sorted(secrets, key=len, reverse=True):
            out = out.replace(secret, "<redacted>")
        return out

    def _transport_error(self, exc: httpx.HTTPError, *more: str | None, retryable: bool = True) -> LoginError:
        """A transport failure in the one shape this process gives one — `<ExceptionType>: <text>`,
        which `is_verify_failure` and the poller's classifier both key on. Whether it may be retried
        is the caller's to say: it depends on whether the password was on the wire, not on the
        exception."""
        raw = f"{type(exc).__name__}: {exc}"
        # DECIDE ON THE RAW MESSAGE, THEN SCRUB THE COPY (third pass: a password of `certificate`
        # scrubbed the phrase the classifier keys on and a TLS failure became `phase=connect`).
        phase = "tls" if is_verify_failure(raw) else "connect"
        return LoginError(UNREACHABLE, self._scrub(raw, *more), phase=phase, retryable=retryable)

    def _log_retry(self, exc: LoginError, attempt: int, *, retry_in: float | None = None,
                   gave_up: bool = False) -> None:
        ceiling = self._policy.attempts
        if gave_up:
            action = (f"gave up after {ceiling} attempts: nothing more is tried until the next lookup or "
                      f"ping — check the API URL, the OAuth route and TLS trust for the OAuth host "
                      f"(the INGRESS CA, which the API's bundle may not carry) from this pod")
        else:
            action = f"retrying in {retry_in:g}s; if every attempt fails, the gave_up line says so"
        failure(log, "fleet-login-failed", phase=exc.phase, outcome=exc.outcome, **self._fields(),
                attempt=f"{attempt}/{ceiling}", retry_in=None if retry_in is None else f"{retry_in:g}",
                gave_up="true" if gave_up else None, action=action, detail=exc.message,
                secrets=(self._password,))

    def _log_stop(self, exc: LoginError) -> None:
        if exc.outcome == AUTH_FAILED:
            failure(log, "fleet-login-refused", phase="credential", outcome=LOGIN_REFUSED, **self._fields(),
                    action=(f"the target refused the password for {self.username}: rotate the fleet "
                            f"password Secret or correct ldapConnectionBootstrap — no second attempt is "
                            f"made, because a retry is the lockout walk against the account the target "
                            f"authenticates every user with"),
                    detail=exc.message, secrets=(self._password,))
            return
        failure(log, "fleet-login-failed", phase=exc.phase, outcome=exc.outcome, **self._fields(),
                action="not retried: fix what detail names before the next lookup or ping",
                detail=exc.message, secrets=(self._password,))
