"""Rejoin (#316, SPEC_D4): a cluster administrator signs in to a remote cluster as themselves, once; the dashboard
reads the poller's token there, writes it here, and forgets the password.

The exchange is the lookup's, started by a person: `RejoinLogin` (#283's login), D8's one question, #284's
`read_sa_token`, the revoke on every exit, and #284's `store` with the person's provenance. What keeps the
password safe, in the order it runs:
  1. the route's host gate (the cluster-admin tier, #322), then `check`: a rejoinable row, a valid username, and
     never a fleet account;
  2. `ONE_TRY`: one authorize per press, and nothing retried;
  3. the poller's `CredentialGate` (#315): a password the directory REFUSED for this exact username is not sent
     again BY THIS POD. A success is not held: two right presses send twice. The gate lives in memory; a durable
     account hold was declined for its operating cost (SPEC_D4, D4-7);
  4. D8: the remote says whether the person is its cluster administrator, and a no reads and writes nothing;
  5. every answer and line is scrubbed of the password, its Basic form, the login's token and the token read.
"""

from __future__ import annotations

import base64
import dataclasses
import json
import logging
import re

from .clusterconfig.events import event, failure
from .clusterconfig.writer import WriteRefused, secret_name_for
from .config import CREDENTIAL_SELF_LOGIN, ClusterConfig, Settings, valid_bootstrap_username
from .fleetlogin import TOKEN_PREFIX, FleetLogin, LoginError, RetryPolicy, _without_userinfo
from .fleetlookup import CredentialGate, LookupRefused, LookupSource, read_sa_token, store
from .fleetlookup import _scrub as _fleet_scrub
from .kube import AUTH_FAILED, UNREACHABLE, ClusterClient, ClusterError
from .timeutil import now_iso

log = logging.getLogger(__name__)

#: The success word. Every other outcome is a refusal's code: the lookup's (`gsd/fleetlookup.py#CODES`) or these three.
REJOINED = "rejoined"
NOT_CLUSTER_ADMIN = "not-cluster-admin"
REVIEW_FAILED = "access-review-failed"
STOPPED = "rejoin-failed"
#: One attempt and no retry, not even before the password is written: a person is waiting, and the next press is the retry.
ONE_TRY = RetryPolicy(attempts=1)
SSAR_API = "/apis/authorization.k8s.io/v1/selfsubjectaccessreviews"
#: What the person reads when the token read refuses (#284's codes); the lookup's own `action` speaks to the fleet.
READ_SAYS = {
    "sa-token-secret-missing": "{cluster} has no poller token Secret to read: create it there first",
    "sa-token-invalidated": "the poller token Secret on {cluster} was invalidated by its legacy-token cleaner: delete "
                            "and recreate it there",
    "sa-token-unreadable": "the poller token Secret on {cluster} could not be used",
}
#: What a quoted text becomes when a secret occurs in it (#465): the whole field, never a span (`_whole`).
QUOTED_MARK = "<redacted: the text contained the credential>"


_HEX = re.compile(r"\\u([0-9a-f]{4})")
#: Go's encoding/json, the remote's own encoder, writes these five as lower-case `\\u` escapes and every other character
#: as is: for any value `check` lets through (no control character, no lone surrogate), Python's non-ASCII spelling
#: with these five replaced is Go's.
_GO = str.maketrans({"<": "\\u003c", ">": "\\u003e", "&": "\\u0026", "\u2028": "\\u2028", "\u2029": "\\u2029"})


def _spellings(value: str) -> set[str]:
    """`value` escaped once, as JSON encoders write it: ASCII or not, `/` as `\\/` or not, `\\u` hex in either case,
    and Go's `encoding/json` default."""
    out = set()
    for ascii_ in (True, False):
        escaped = json.dumps(value, ensure_ascii=ascii_)[1:-1]
        for form in (escaped, escaped.replace("/", "\\/")):
            out |= {form, _HEX.sub(lambda m: "\\u" + m[1].upper(), form)}
    out.add(json.dumps(value, ensure_ascii=False)[1:-1].translate(_GO))
    return out


def _scrub(text: str, secrets) -> str:
    """The fleet's scrub, handed each secret as written and in its `_spellings` once and twice escaped: a remote may
    quote a JSON document inside another, and the shared escaped forms stop at eight characters, while a person's
    password may be three. It covers accidental echoes; a hostile remote holds the password anyway (SPEC_D4 §3.7)."""
    forms = set()
    for secret in filter(None, secrets):
        layer = {secret}
        forms |= layer
        for _ in range(2):
            layer = set().union(*map(_spellings, layer))
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


class RejoinLogin(FleetLogin):
    """#283's login as the person who pressed Rejoin: the same wire, events and rules, in a person's words."""

    REFUSED_ACTION = ("check the username and password — it is not sent again by this pod while it is the same "
                      "password, because each refused try counts toward the directory's lockout of the account")
    NEXT_TRY = "the next Rejoin"

    def __init__(self, cluster: ClusterConfig, username: str, password: str, *, person: str, **knobs):
        super().__init__(cluster, username, password, **knobs)
        self.person = person

    def _scrub(self, text: str, *more: str | None) -> str:
        # FleetLogin scrubs every remote text with this before cutting it; the fleet's own scrub stays as it is.
        return _scrub(text, (self._password, *self._secrets, *more))

    def _fields(self) -> dict[str, str]:
        return {**super()._fields(), "rejoin_by": self.person}


def refusal(cluster: ClusterConfig, settings: Settings) -> str | None:
    """Why this cluster cannot be rejoined, or None: Secret rows and `saTokenLookup` stanzas only (the epic's decision,
    SPEC_D4 §3.2). `/api/clusterconfigs` serves it as `rejoinable`, so the page and the route answer alike."""
    host = settings.host_cluster()
    if host is not None and cluster.name == host.name:
        return "the host polls as the pod's own ServiceAccount; there is no token to fetch"
    if cluster.onboarding or cluster.source.startswith("configmap:"):
        return "a ConfigMap declares it, and its Secret is generated from the stanza there"
    if cluster.credential_kind == CREDENTIAL_SELF_LOGIN:
        return "it declares userSelfLogin: its credential is a session, and a stored token would replace that mode"
    if cluster.source.startswith("secret:") or cluster.sa_token_lookup:
        return None
    return "the chart's values give it its own credential, and a Secret would shadow that entry"


def fleet_accounts(settings: Settings) -> set[str]:
    """Every account a fleet path may present the fleet password as: the chart's, each stanza's
    `ldapConnectionBootstrap`, each Secret's `lookup-account`. Stripped and casefolded: over-refusing is the safe side."""
    names = {settings.fleet_account_username}
    for c in (*settings.clusters, *settings.effective_clusters()):
        names.update((c.ldap_connection_bootstrap, c.lookup_account))
    return {name.strip().casefold() for name in names if name}


def check(cluster: ClusterConfig, settings: Settings, username: str, password: str) -> None:
    """The refusals made before anything is sent (SPEC_D4 §3.1). Each is a `WriteRefused`; none repeats a value."""
    reason = refusal(cluster, settings)
    if reason is not None:
        raise WriteRefused("not-rejoinable", f"{cluster.name} cannot be rejoined: {reason}", conflict=True)
    if not valid_bootstrap_username(username):
        raise WriteRefused("rejoin-username-invalid", "a username is letters, digits and . _ @ -, starting with a letter "
                                                      "or digit, at most 255 characters (RFC 7617 forbids a colon and "
                                                      "control characters); the value is not repeated")
    if username.casefold() in fleet_accounts(settings):
        raise WriteRefused("rejoin-fleet-account", "that username is an account the dashboard's fleet paths log in as; "
                                                   "Rejoin takes a person's own account, never the fleet account")
    if not password:
        raise WriteRefused("rejoin-password-missing", "a password is required")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F or 0xD800 <= ord(ch) <= 0xDFFF for ch in password):
        raise WriteRefused("rejoin-password-invalid", "the password holds a control character, which RFC 7617 forbids, "
                                                      "or an unpaired surrogate, which UTF-8 cannot carry; it was not "
                                                      "sent")
    # #447: the scrub replaces the password wherever it occurs, the username included, so a password inside the
    # username leaves a redacted span that IS the password. Stripped, because `redact_text` strips what it matches.
    folded = password.strip().casefold()
    if folded and folded in username.casefold():
        raise WriteRefused("rejoin-password-within-username", "the password must not be the username or a part of it, "
                                                             "ignoring case and surrounding spaces; it was not sent")


def question(settings: Settings) -> dict[str, str]:
    """#322's cluster-admin question as a review's resourceAttributes, built as the host's `TierResolver` builds it."""
    attrs = {"verb": settings.visibility_cluster_admin_sar_verb,
             "resource": settings.visibility_cluster_admin_sar_resource,
             "group": settings.visibility_cluster_admin_sar_api_group}
    if settings.visibility_cluster_admin_sar_namespace:
        attrs["namespace"] = settings.visibility_cluster_admin_sar_namespace
    if settings.visibility_cluster_admin_sar_subresource:
        attrs["subresource"] = settings.visibility_cluster_admin_sar_subresource
    return attrs


def question_words(settings: Settings) -> str:
    """The question as the answer and the log say it: `update clusterrolebindings`."""
    attrs = question(settings)
    resource = "/".join(part for part in (attrs["resource"], attrs.get("subresource")) if part)
    where = f" in namespace {attrs['namespace']}" if attrs.get("namespace") else ""
    return f"{attrs['verb']} {resource}{where}"


class _ReviewClient(ClusterClient):
    """D8's client: `_send` cuts a failed answer's body at 200 characters after `_redact`, so Rejoin's scrub runs here."""

    secrets: tuple[str, ...] = ()

    def _redact(self, text: str, *more: str | None) -> str:
        return _scrub(super()._redact(text, *more), self.secrets)


def remote_says_cluster_admin(session_token: str, cluster: ClusterConfig, settings: Settings, *,
                              timeout: float, secrets=()) -> tuple[bool, str]:
    """D8: one SelfSubjectAccessReview on the remote, sent with the login's own token, so the remote answers for the
    person and the groups it resolves for them. (allowed, the remote's reason). Only a boolean `status.allowed` is an
    answer; anything else raises ClusterError, and the caller refuses: no answer is never a yes."""
    as_session = dataclasses.replace(cluster, token_value=session_token, sa_token_lookup=False, user_self_login=False,
                                     ldap_connection_bootstrap=None)
    remote = _ReviewClient(as_session, timeout=timeout)
    remote.secrets = tuple(secrets)
    body = {"apiVersion": "authorization.k8s.io/v1", "kind": "SelfSubjectAccessReview",
            "spec": {"resourceAttributes": question(settings)}}
    with remote._client() as client:
        answer = remote._send(client, "POST", SSAR_API, json=body)
    status = answer.get("status") if isinstance(answer, dict) else None
    allowed = status.get("allowed") if isinstance(status, dict) else None
    if not isinstance(allowed, bool):
        raise ClusterError(UNREACHABLE, f"{SSAR_API} answered without a boolean status.allowed")
    return allowed, "; ".join(str(status[key]) for key in ("reason", "evaluationError") if status.get(key))


def rejoin(cluster: ClusterConfig, settings: Settings, host_client: ClusterClient, *, own_namespace: str,
           gate: CredentialGate, username: str, password: str, viewer: str) -> dict:
    """One Rejoin, after `check`: the gate, the login, D8, the read, the revoke, the write. Answers `{outcome, message,
    at}`: `rejoined`, or a refusal's code with the person's sentence. The caller holds the one-at-a-time lock, so the
    gate's check and the login it guards are one step in this process."""
    # The password as the Basic header carries it (RFC 7617): a remote that quotes the header quotes this.
    secrets = [password, base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")]
    login = RejoinLogin(cluster, username, password, person=viewer, timeout=settings.request_timeout_seconds,
                        policy=ONE_TRY)
    try:
        return _exchange(cluster, settings, host_client, own_namespace=own_namespace, gate=gate, username=username,
                         password=password, viewer=viewer, login=login, secrets=secrets)
    except Exception:  # noqa: BLE001 - its text may quote the password: fixed words, then how the login ended
        return stopped_unexpectedly(cluster.name, viewer, cleanup=_logged_out(login, cluster), secrets=secrets)


def _exchange(cluster: ClusterConfig, settings: Settings, host_client: ClusterClient, *, own_namespace: str,
              gate: CredentialGate, username: str, password: str, viewer: str, login: RejoinLogin,
              secrets: list[str]) -> dict:
    """`rejoin`'s steps, inside its boundary, which keeps the login to say how it ended."""
    timeout = settings.request_timeout_seconds
    asked = question_words(settings)
    who = dict(cluster=cluster.name, by=viewer, account=username)

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

    answered = gate.account_refusal(username, password)
    if answered is not None:
        shown = _without_userinfo(answered) or "an earlier cluster"
        return refused("login-refused", f"{shown} already refused this password for {username}, so it was not sent: "
                                        f"type the right password (this pod holds a refused password back until it "
                                        f"restarts)")
    stopped: tuple[str, str, str | None] | None = None      # D8 refused, or could not be asked
    try:
        with login as session:
            secrets.append(session.token)
            try:
                allowed, reason = remote_says_cluster_admin(session.token, cluster, settings, timeout=timeout,
                                                            secrets=secrets)
            except ClusterError as exc:
                stopped = (REVIEW_FAILED, f"{cluster.name} could not be asked whether {username} may {asked} there, "
                                          f"so nothing was read or written", f"{exc.outcome}: {exc.message}")
            else:
                event(log, logging.INFO, "cluster-rejoin-review", **who, question=asked,
                      allowed="true" if allowed else "false", reason=_quoted(reason, secrets) or None, secrets=secrets)
                if not allowed:
                    stopped = (NOT_CLUSTER_ADMIN, f"{cluster.name} says {username} may not {asked} there, so nothing "
                                                  f"was read or written: Rejoin needs a cluster administrator of "
                                                  f"{cluster.name}", reason or None)
                else:
                    try:
                        sa_token = read_sa_token(session.token, cluster, LookupSource.from_settings(settings),
                                                 timeout=timeout)
                    except LookupRefused as exc:
                        login.add_secrets(*exc.secrets)   # the revoke on leaving `with` runs before any outer handler
                        raise
                    secrets.append(sa_token.token)
                    login.add_secrets(sa_token.token)   # the revoke line quotes the remote's body too
    except LoginError as exc:
        if exc.bound:
            # THE PASSWORD WAS ON THE WIRE (#283): the account's entry, exactly as the lookup writes it (#315).
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
    at = now_iso()
    try:
        written = store(host_client, own_namespace, cluster, settings, sa_token, account=username,
                        rejoin=(viewer, username, at))
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


def stopped_unexpectedly(cluster: str, viewer: str, *, cleanup: str = "", secrets=()) -> dict:
    """The answer to an error the design did not expect: fixed words, because the error's own may quote the password,
    then how the login ended when there was one. The line records only that it happened."""
    said = _scrub("Rejoin stopped unexpectedly, and nothing of the error is shown or logged: press Refresh before "
                  f"Rejoin again{cleanup}", secrets)
    failure(log, "cluster-rejoin-failed", phase="credential", outcome=STOPPED, cluster=cluster, by=viewer, action=said,
            secrets=secrets)
    return {"outcome": STOPPED, "message": said, "at": now_iso()}


def _logged_out(login: FleetLogin, cluster: ClusterConfig) -> str:
    """How the login ended, for every answer after a session existed: revoked, or what to delete. An unprefixed
    token is its own object's name, so it is never shown (`gsd/fleetlogin.py#token_object_name`)."""
    if login.session is None:
        return ""
    if login.revoked:
        return "; the login was signed out"
    name = login.session.token_name if login.session.token.startswith(TOKEN_PREFIX) else "the login's token"
    return (f"; the login could NOT be signed out on {cluster.name}: delete {name} there (oc delete "
            f"useroauthaccesstokens <name>, as yourself)")


__all__ = ["NOT_CLUSTER_ADMIN", "ONE_TRY", "QUOTED_MARK", "READ_SAYS", "REJOINED", "REVIEW_FAILED", "STOPPED",
           "RejoinLogin", "check", "fleet_accounts", "question", "question_words", "refusal", "rejoin",
           "remote_says_cluster_admin", "stopped_unexpectedly"]
