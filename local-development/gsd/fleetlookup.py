"""Retrieve a cluster's credential as the fleet account — the lookup of #284 (SPEC_S4b).

THE LOOP, and this module is its one missing stage: a values stanza (or a Secret) declares
`saTokenLookup: true`; this module logs in to that cluster as the fleet account (`gsd/fleetlogin.py`,
#283), reads the poller ServiceAccount's PERMANENT token from its `kubernetes.io/service-account-token`
Secret there — one GET, by name, the only read the estate's `resourceNames` grant allows — and hands
the token to the shipped writer, which produces `gsd-cluster-<name>` in this release's namespace with
the discovery label on it. Discovery then polls the cluster like any other. Two identities, neither
granted anything on the other side: the LDAP account reads REMOTELY, the pod's ServiceAccount writes
LOCALLY.

WHAT IS WRITTEN IS THE VALUES, NOT THE SHAPE (chart 0.49.0 ships the shape): `token-source`
remote-lookup, the source namespace and ServiceAccount, `managed-by` sa-token-lookup, and the account
the login used. The Secret's trust is the DECLARATION's — a `caBundleFile`, a declaring Secret's
`caData`, `insecure`, or the trusted bundle — because that bundle just verified BOTH hosts the login
touches (the API host and the OAuth route), and the target's own `ca.crt` verifies only the first.

NOTHING HERE REVOKES. The stored token is the target's and dies only with its Secret; the login's
own token is revoked by `FleetLogin.__exit__` on every path, including a failed read.

THE ONE-YEAR FUSE, read rather than assumed: Kubernetes' legacy-token cleaner stamps
`kubernetes.io/legacy-token-invalid-since` on an AUTO-GENERATED token Secret (one the ServiceAccount's
`.secrets` references) unused for `--legacy-service-account-token-clean-up-period` (8760h), and the
API server then refuses the token. A manually created Secret is not referenced and is never stamped;
one that carries the label is already dead, and storing it would be a 401 on the first poll.

`lookup(..., write=False)` is #285's daily ping: the same login, read and revoke, and nothing stored.

THE ACCOUNT LEASE (#285, SPEC_S4c §3.3). A caller that passes `lease` has CLAIMED the fleet account's Lease
first: its entry for this password gates here like the process's own, and a bound answer is written to it
before the process's gate, so a restart and a second replica read what this process was told.
"""

from __future__ import annotations

import base64
import binascii
import dataclasses
import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import httpx

from .clusterconfig.writer import (
    MANAGED_BY_LOOKUP, MANAGED_BY_ONBOARD, MANAGED_BY_UI, TOKEN_SOURCE_LOOKUP, TOKEN_SOURCE_REJOIN, CreateRequest, WriteFailed,
    WriteRefused, create, secret_name_for, store_lookup,
)
from .clusterconfig.events import is_transport_message, redact
from .config import ClusterConfig, Settings
from .fleetlogin import FleetLogin, LoginError, _without_userinfo
from .fleetstate import FleetLease, lease_digest
from .kube import AUTH_FAILED, ClusterClient, ClusterError, redact_text

log = logging.getLogger(__name__)

SA_TOKEN_SECRET_TYPE = "kubernetes.io/service-account-token"
SA_NAME_ANNOTATION = "kubernetes.io/service-account.name"
#: Stamped by the API server on every use of a legacy token (pkg/serviceaccount/legacy.go, Validate).
LAST_USED_LABEL = "kubernetes.io/legacy-token-last-used"
#: Stamped by the cleaner on an auto-generated token unused for the period; the token is refused after.
INVALID_SINCE_LABEL = "kubernetes.io/legacy-token-invalid-since"
#: The schedule the poller runs this under (SPEC_S4b, orchestrator's notes): a failure that SPENT a
#: login counts, `attempt=n/5`, the next try discovery_interval × 2^(n−1) later, capped at a day, then
#: gave up out loud until the declaration changes, the pod restarts or #285 re-arms it.
LOOKUP_ATTEMPTS = 5
LOOKUP_WAIT_CAP = 86400.0
#: Every finding code this module raises; each is in `clusterconfig.FINDING_CODES`.
CODES = ("fleet-credential-missing", "fleet-write-disabled", "login-refused", "login-failed",
         "sa-token-secret-missing", "sa-token-unreadable", "sa-token-invalidated", "lookup-write-failed")


class LookupRefused(Exception):
    """One step of the lookup refused, typed as the finding it becomes.

    `code` is in CODES; `detail` says what happened and `action` what to change (#245: the fix, not
    the diagnosis), neither ever a credential; `spent` is whether a login was attempted — the
    poller's schedule counts spent failures and rechecks the free ones every cycle; `gated` is the
    free refusal the gate gives — terminal until the credential changes, said once with
    `gave_up=true` (third pass, R3-2); `secrets` are the values in play, for the emit helper to
    strip from the line the poller writes.
    """

    def __init__(self, code: str, detail: str, *, action: str, spent: bool, gated: bool = False,
                 secrets: tuple[str, ...] = ()):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail, self.action, self.spent, self.gated = code, detail, action, spent, gated
        self.secrets: tuple[str, ...] = tuple(secrets)

    def scrub(self, secrets: list[str]) -> None:
        """Every secret in play out of `detail`, `action` AND `args` — `str(exc)` is what a caller
        that did not read the fields prints (review of #295, P1-1)."""
        self.secrets = tuple(v for v in (*self.secrets, *secrets) if v)
        self.detail, self.action = _scrub(self.detail, list(self.secrets)), _scrub(self.action, list(self.secrets))
        self.args = (f"{self.code}: {self.detail}",)


class CredentialGate:
    """SPEC_S4 §6's in-memory half: a password the directory evaluated — or may have — is not sent
    again while it is the same password. Two kinds of entry (#315, SPEC_S4d):

    REFUSED, keyed on (username, sha256(password)[:16]) — the ACCOUNT, never the target. Every
    `LoginError.bound` answer writes it, a 401 and a 500 alike: a directory locks out per account,
    and a locked account's 500 (LDAP code 19) cannot be told from a sick target's 500. The operator's
    ruling at the review of #325 (SPEC_S4c, orchestrator's notes), reversing R2-1 of #295's second
    pass; the price is that one sick target's 500 stops every target of the account until the
    password rotates or the process restarts (SPEC_S4c §5, question 7). The target that answered is
    kept as evidence and named in the gated refusal.

    SPENT, keyed on (target, username, digest) — #293's success mark (SPEC_S5 §3.3): a successful
    ConfigMap session spends THAT target's budget, so onboarding one cluster never gates another.

    The digest, because the password is not in the declaration: rotating the Secret changes no
    stanza and must re-arm both kinds by itself. It is 64 bits ON PURPOSE — a collision over-blocks,
    never binds again; so does one username and password shared by two directories, the safe
    direction, stated and not solved.

    THE BUDGET, with its scope: at most one answered failed authorize per (account, password) per
    process, across every target. "Account" is the exact configured username string, compared as
    written: directory aliases and case variants are not resolved, so every stanza for one identity
    must use one spelling. "Process" is the production Poller's one gate, shared by its discovery
    thread and its self-login poll threads (single dict and set operations); a new gate starts a new
    budget. It is the cache of the account Lease's gate (SPEC_S4c §3.3): every bind path claims the
    Lease first, seeds the REFUSED kind from the Lease's entry, and records its attempt there before
    the password is sent; a bound answer replaces that record before it is written here — so a
    restart, a crash and a second replica read it while the Lease is writable, and this is the only
    copy when it is not. The SPENT kind is never on the Lease, and self-login and the read-only ping
    ask for the REFUSED kind alone (`account_refusal`)."""

    def __init__(self) -> None:
        self._refused: dict[tuple[str, str], str] = {}
        self._spent: set[tuple[str, str, str]] = set()

    @staticmethod
    def _target(target: str) -> str:
        # THE TARGET AS httpx CANONICALISES IT (third pass, R3-1): host case and IDNA, not a whole-string
        # lowercase that would mangle a path or a port. `api.example.com` and `API.example.com/` are one
        # target. A malformed URL falls back to the bare string: the gate must never raise.
        try:
            return str(httpx.URL(target)).rstrip("/")
        except httpx.InvalidURL:
            return target.rstrip("/")

    @staticmethod
    def _digest(password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()[:16]

    def account_refusal(self, username: str, password: str) -> str | None:
        """The REFUSED kind alone: the target that answered for this account and password, or None. Self-login and
        the read-only ping ask this — #293's SPENT mark is a writing lookup's budget, never an account refusal
        (#285, review of #419, F2)."""
        return self._refused.get((username, self._digest(password)))

    def answered(self, target: str, username: str, password: str) -> str | None:
        """The target whose answer gates this password for this account on `target`, or None: the
        account's REFUSED entry from whichever target answered, else `target`'s own SPENT entry."""
        digest = self._digest(password)
        refused = self._refused.get((username, digest))
        if refused is not None:
            return refused
        canonical = self._target(target)
        return canonical if (canonical, username, digest) in self._spent else None

    def refused(self, target: str, username: str, password: str) -> bool:
        return self.answered(target, username, password) is not None

    def refuse(self, target: str, username: str, password: str) -> None:
        """A bound failure: the account's entry, whatever target answered; the first answer stays the evidence."""
        self._refused.setdefault((username, self._digest(password)), self._target(target))

    def spend(self, target: str, username: str, password: str) -> None:
        """#293's success mark: this target's entry only."""
        self._spent.add((self._target(target), username, self._digest(password)))


@dataclass(frozen=True)
class LookupSource:
    """Where the token is read on every target — one convention for the fleet (the operator chart's)."""

    namespace: str
    service_account: str
    secret_name: str

    @classmethod
    def from_settings(cls, settings: Settings) -> LookupSource:
        sa = settings.sa_token_lookup_service_account
        return cls(settings.sa_token_lookup_namespace, sa, settings.sa_token_lookup_secret_name or f"{sa}-token")


@dataclass(frozen=True)
class SaToken:
    """What the target's Secret held: the token, whose it is, and the cleaner's last-used stamp."""

    token: str = field(repr=False, compare=False)
    namespace: str = ""
    service_account: str = ""
    secret_name: str = ""
    last_used: str | None = None


@dataclass(frozen=True)
class LookupResult:
    cluster: str
    account: str
    sa_token: SaToken
    secret: str
    written: str | None
    """`created` (a values stanza), `updated` (a declaring Secret), or None when `write=False`."""
    secrets: tuple[str, ...] = field(repr=False, compare=False, default=())


def _status_only(message: str) -> str:
    """A `ClusterError` message without any remote body: `HTTP 500 on /path: <body>` becomes
    `HTTP 500 on /path`. A body is remote-controlled and can carry the very token this lookup is
    reading, which was never decoded and so is not among the secrets a refusal is scrubbed against
    (review of #295, second pass, R2-3). A transport message is this process's own words and is kept."""
    return message if is_transport_message(message) else message.split(": ", 1)[0]


def _scrub(text: str, secrets: list[str]) -> str:
    """Every secret in play out of free text, in the spellings the two helpers know and then, whatever
    its length, the raw value — `fleetlogin.FleetLogin._scrub`'s rule, applied at this module's one
    boundary rather than at every quoting site."""
    values = tuple(v for v in secrets if v)
    out = redact(redact_text(text, *values), values)
    for value in sorted(values, key=len, reverse=True):
        out = out.replace(value, "<redacted>")
    return out


def fleet_account(settings: Settings, cluster: ClusterConfig) -> str:
    """The stanza's `ldapConnectionBootstrap`, else the chart's fleet username (SPEC_S3 §3.1 rule 1)."""
    username = cluster.ldap_connection_bootstrap or settings.fleet_account_username
    if not username:
        raise LookupRefused("fleet-credential-missing", f"no fleet account is named for {cluster.name}",
                            action=("set clusterConfig.fleetAccount.username, or ldapConnectionBootstrap on the "
                                    "cluster's stanza"), spent=False)
    return username


def fleet_password(host_client: ClusterClient, settings: Settings, own_namespace: str) -> tuple[str, str]:
    """The password and the Secret's `metadata.uid` — the Lease fingerprint's salt (`gsd/fleetstate.py#lease_digest`)
    — read now, in one GET, through the chart's one-Secret grant (`templates/fleet-account-rbac.yaml`); never held on
    Settings or ClusterConfig, so `poller._credentials` never sees it."""
    ns = settings.fleet_password_secret_namespace or own_namespace
    name, key = settings.fleet_password_secret_name, settings.fleet_password_secret_key
    where = f"Secret {ns}/{name} key {key!r}"
    action = ("put the fleet account's password in that Secret and key (clusterConfig.fleetAccount.passwordSecret), "
              "and let the chart render its grant (passwordSecret.rbac.create) or grant get on it by hand")
    try:
        with host_client._client() as client:
            obj = host_client._get(client, f"/api/v1/namespaces/{ns}/secrets/{name}", {})
    except ClusterError as exc:
        raise LookupRefused("fleet-credential-missing", f"cannot read {where}: {exc.outcome}: {_status_only(exc.message)}",
                            action=action, spent=False) from exc
    try:
        password = base64.b64decode((obj.get("data") or {}).get(key) or "", validate=True).decode("utf-8").strip()
    except (binascii.Error, UnicodeDecodeError, ValueError):
        password = ""
    if not password:
        raise LookupRefused("fleet-credential-missing", f"{where} is absent or empty", action=action, spent=False)
    uid = str((obj.get("metadata") or {}).get("uid") or "")
    if not uid:   # every object an API server returns has one: fail closed rather than salt with less (#419, D2)
        raise LookupRefused("fleet-credential-missing", f"{where} carries no metadata.uid", action=action, spent=False)
    return password, uid


def read_sa_token(session_token: str, cluster: ClusterConfig, source: LookupSource, *, timeout: float) -> SaToken:
    """GET the token Secret on the TARGET as the session — the read #285's ping reuses.

    `ClusterClient` with the session as the credential: the same TLS decision as the login
    (`ClusterConfig.verify()`), the same outcome words, and its own token scrubbed from what it
    quotes. The Secret is read BY NAME with `get` — the estate grants `get` on that one Secret by
    `resourceNames` and refuses `list`, and a manually created token Secret is not in the
    ServiceAccount's `.secrets`, so neither a list nor the SA can find it (measured, SPEC_S4b §2).
    """
    as_session = dataclasses.replace(cluster, token_value=session_token, sa_token_lookup=False,
                                     user_self_login=False, ldap_connection_bootstrap=None)
    path = f"/api/v1/namespaces/{source.namespace}/secrets/{source.secret_name}"
    where = f"Secret {source.namespace}/{source.secret_name} on {cluster.name}"
    reader = ClusterClient(as_session, timeout=timeout)
    try:
        with reader._client() as client:
            obj = reader._get(client, path, {})
    except ClusterError as exc:
        if exc.message.startswith("HTTP 404"):
            raise LookupRefused(
                "sa-token-secret-missing", f"{where} does not exist",
                action=(f"create the token Secret on the target: OpenShift 4.16+ and Kubernetes 1.24+ no longer "
                        f"create one, so it is an onboarding step — a kubernetes.io/service-account-token Secret "
                        f"named {source.secret_name} annotated {SA_NAME_ANNOTATION}={source.service_account}, "
                        f"which the control plane then fills"), spent=True) from exc
        raise LookupRefused("sa-token-unreadable", f"{where}: {exc.outcome}: {_status_only(exc.message)}",
                            action=("grant the fleet account get on that one Secret on the target (resourceNames), "
                                    "and check the ServiceAccount and Secret names in clusterConfig.saTokenLookup"),
                            spent=True) from exc
    meta = obj.get("metadata") or {}
    labels, annotations = meta.get("labels") or {}, meta.get("annotations") or {}
    # THE TOKEN IS DECODED FIRST (review of #295, P1-1): whatever this function refuses below, the
    # token the Secret carried rides the refusal's `secrets`, so no quoted field can carry it out.
    # `TypeError` too (second pass, R2-3): a non-scalar `data.token` must be a refusal, not a crash
    # in front of the refusals this decode exists to feed.
    try:
        token = base64.b64decode((obj.get("data") or {}).get("token") or "", validate=True).decode("utf-8").strip()
    except (binascii.Error, UnicodeDecodeError, ValueError, TypeError):
        token = ""
    carried = (token,) if token else ()
    # A remote-controlled NAME is described by its length, never echoed — the parser's rule for a key
    # this contract does not know (`parser._unknown_key`), applied to the type and the owner.
    kind = obj.get("type")
    if kind != SA_TOKEN_SECRET_TYPE:
        raise LookupRefused("sa-token-unreadable", f"{where} is not type {SA_TOKEN_SECRET_TYPE} (its type is "
                                                   f"{len(str(kind or ''))} characters long); not stored",
                            action="point clusterConfig.saTokenLookup.tokenSecretName at the ServiceAccount's token Secret",
                            spent=True, secrets=carried)
    owner = annotations.get(SA_NAME_ANNOTATION)
    if owner != source.service_account:
        raise LookupRefused("sa-token-unreadable", f"{where} is not {source.service_account!r}'s: its "
                                                   f"{SA_NAME_ANNOTATION} annotation is {len(str(owner or ''))} characters "
                                                   f"long and does not match; not stored",
                            action="check clusterConfig.saTokenLookup.sourceServiceAccount against the Secret's annotation",
                            spent=True, secrets=carried)
    if INVALID_SINCE_LABEL in labels:
        # PRESENCE, not truthiness (review of #295, P1-5): Kubernetes allows an empty label value.
        raise LookupRefused("sa-token-invalidated", f"{where} carries the {INVALID_SINCE_LABEL} label: the target's "
                                                    f"legacy-token cleaner invalidated it after a year unused and the API "
                                                    f"server refuses it; not stored",
                            action=("delete and recreate the token Secret on the target (the control plane fills the new "
                                    "one), or remove that label to allow the token temporarily"), spent=True, secrets=carried)
    if not token:
        raise LookupRefused("sa-token-unreadable", f"{where} has no token yet",
                            action="the token controller fills a new Secret within seconds; nothing to do unless it stays empty",
                            spent=True)
    return SaToken(token=token, namespace=source.namespace, service_account=source.service_account,
                   secret_name=source.secret_name, last_used=labels.get(LAST_USED_LABEL))


def declared_trust(cluster: ClusterConfig) -> tuple[str, str | None]:
    """(tls_mode, ca_data) for the Secret the values path writes: THE DECLARATION'S trust, verbatim.

    It is the bundle that just verified the API host (discovery) and the OAuth route (authorize), so
    it is proven for the poll and for a re-login alike; the target's `ca.crt` verifies only the API
    host and is deliberately not written (SPEC_S4b, orchestrator's notes).
    """
    if cluster.insecure_skip_verify:
        return "insecure", None
    if cluster.ca_bundle_file:
        try:
            return "caData", base64.b64encode(Path(cluster.ca_bundle_file).read_bytes()).decode("ascii")
        except OSError as exc:
            raise LookupRefused("lookup-write-failed", f"cannot read caBundleFile {cluster.ca_bundle_file!r}: {exc}",
                                action="fix the caBundleFile the stanza names", spent=True) from exc
    return "trustedBundle", None


def store(host_client: ClusterClient, own_namespace: str, cluster: ClusterConfig, settings: Settings,
          sa_token: SaToken, *, account: str, rejoin: tuple[str, str, str] = ()) -> str:
    """Write the credential where the declaration says (SPEC_S4 §1): a values stanza gets a new
    `gsd-cluster-<name>` through `writer.create`; a declaring Secret is updated in place through
    `writer.store_lookup`. Returns `created` or `updated`. `rejoin` is (who pressed, the account, the
    instant) for a person's Rejoin (SPEC_D4): the same write, with the person's provenance."""
    provenance = dict(source_namespace=sa_token.namespace, source_service_account=sa_token.service_account,
                      lookup_account=None if rejoin else account, rejoin=rejoin)
    try:
        if cluster.source.startswith("secret:"):
            store_lookup(host_client, own_namespace, cluster.source.split(":", 1)[1], token=sa_token.token,
                         cluster=cluster.name, **provenance)
            return "updated"
        tls_mode, ca_data = declared_trust(cluster)
        visibility, identity = settings.cluster_policy(cluster.name)
        managed_by = MANAGED_BY_UI if rejoin else MANAGED_BY_ONBOARD if cluster.onboarding else MANAGED_BY_LOOKUP
        req = CreateRequest(name=cluster.name, server=cluster.api_url, credential_kind="bearerToken",
                            token=sa_token.token, tls_mode=tls_mode, ca_data=ca_data,
                            visibility=visibility, identity=identity, enabled=cluster.enabled,
                            managed_by=managed_by, onboarding=cluster.onboarding,
                            token_source=TOKEN_SOURCE_REJOIN if rejoin else TOKEN_SOURCE_LOOKUP, **provenance)
        # `taken` without this cluster: the stanza IS the entry the Secret is written for.
        taken = {c.name: c.source for c in settings.effective_clusters() if c.name != cluster.name}
        host = settings.host_cluster()
        create(host_client, own_namespace, req, host_name=host.name if host else None, taken=taken,
               viewer=rejoin[0] if rejoin else MANAGED_BY_LOOKUP)
        return "created"
    except WriteRefused as exc:
        raise LookupRefused("lookup-write-failed", f"{exc.code}: {exc.detail}",
                            action=("fix or delete the Secret named, then the next attempt writes it — the credential was "
                                    "read and not stored"), spent=True) from exc
    except WriteFailed as exc:
        raise LookupRefused("lookup-write-failed", f"{exc.outcome}: {exc.message}",
                            action="check the write grant (clusterConfig.secrets.writes.enabled) and the API server", spent=True) from exc


def lookup(cluster: ClusterConfig, settings: Settings, host_client: ClusterClient, *, own_namespace: str,
           gate: CredentialGate, write: bool = True, sleep: Callable[[float], None] = time.sleep,
           clock: Callable[[], datetime] | None = None, lease: FleetLease | None = None,
           held: tuple[str, ...] = ()) -> LookupResult:
    """The whole retrieval for one cluster: password, login, read, revoke, and — with `write` — store.

    Every refusal is a `LookupRefused` carrying the finding it becomes and the secrets in play. The
    session is a context manager, so the login's token is revoked whatever the read does. With
    `write=False` (#285's ping) nothing is written and the token is returned in the result. `lease` is
    the fleet account's Lease with the caller's claim on it (SPEC_S4c §3.3); every production caller
    passes one, and None is the process's gate alone — #284's and #293's own hermetic tests. `held` are values this
    process holds that the target may echo — the ping's stored token for the very cluster it logs in to, and every
    self-login session (#419, D4) — scrubbed from every line and every refusal, and never sent.
    """
    if write and not (settings.cluster_secrets_enabled and settings.cluster_secrets_writes_enabled):
        # THE SWITCH IS CHECKED HERE, not only by the caller (review of #295, P1-4): a second caller —
        # #285's ping with write=True, #293's feed — must not bypass it. Before any password is read.
        raise LookupRefused("fleet-write-disabled", f"{cluster.name} declares saTokenLookup but this deployment does not "
                                                    f"write cluster Secrets",
                            action=("set clusterConfig.secrets.writes.enabled: true (and secrets.enabled) — the lookup "
                                    f"writes {secret_name_for(cluster.name)}, and create/update on Secrets is the grant "
                                    "that switch renders"), spent=False)
    source = LookupSource.from_settings(settings)
    account = fleet_account(settings, cluster)
    password, salt = fleet_password(host_client, settings, own_namespace)
    digest = lease_digest(account, password, salt) if lease is not None else ""
    secrets: list[str] = [password, *held]
    try:
        if lease is not None:
            # THE LEASE SEEDS THE PROCESS'S GATE (SPEC_S4c §3.3): an entry another replica, or this pod before
            # a restart, wrote for this account and password gates here too, naming the target that answered.
            entry = lease.record.gated(digest)
            if entry is not None:
                gate.refuse(entry.get("target") or "", account, password)
        # A writing lookup asks the combined gate — #293's per-target SPENT mark included; the read-only ping asks
        # for an account refusal alone (review of #419, F2).
        answered = (gate.answered(cluster.api_url, account, password) if write
                    else gate.account_refusal(account, password))
        if answered is not None:
            # THE TARGET THAT ANSWERED IS NAMED (#315): the entry is the account's, so it may be another
            # cluster's answer that stops this one, and the finding must say where to look. Shown without
            # userinfo, query or fragment: a values `apiUrl` is not held to the Secret contract's
            # no-credential URL rule, and the gate's evidence keeps whatever the stanza wrote.
            shown = _without_userinfo(answered) or "the answering target (not shown: its URL is not https with a host)"
            raise LookupRefused("login-refused", f"{shown} evaluated this password for {account} already and it "
                                                 f"has not changed; {cluster.name} does not send it",
                                action=("not tried again until the fleet password Secret or the account the stanza names "
                                        "changes — rotate the Secret, or correct ldapConnectionBootstrap; the password is "
                                        "re-read each cycle at no cost and the login resumes when it moves (SPEC_S4 §6)"),
                                spent=False, gated=True)
        if lease is not None:
            # THE ATTEMPT IS ON THE LEASE BEFORE THE PASSWORD IS ON THE WIRE (SPEC_S4c §3.3, step 3): from here a crash,
            # a lost refusal write, a restart or a second process finds it. ClaimHeld and FleetStateUnavailable are
            # the caller's, as they are for the claim.
            lease.reserve(CredentialGate._target(cluster.api_url), digest)
        knobs = {"clock": clock} if clock is not None else {}
        login = FleetLogin(cluster, account, password, timeout=settings.request_timeout_seconds, sleep=sleep,
                           secrets=held, **knobs)
        try:
            with login as session:
                if lease is not None:
                    lease.complete()   # a session came back: the attempt's entry goes, whatever the read does (#293)
                secrets.append(session.token)
                if cluster.onboarding:
                    # #293's strict budget includes successful binds, even if the later read/write fails.
                    # Keep the SAME process-lifetime gate used by every existing lookup caller — THIS
                    # target's entry only: a success elsewhere must not gate another cluster (#315).
                    gate.spend(cluster.api_url, account, password)
                # THE TOKEN READ IS HANDED TO THE LOGIN BEFORE THE REVOKE RUNS (#440): leaving `with` revokes the
                # session, and that line quotes the remote's answer — which may echo the token this process now
                # holds. A read the lookup REFUSED after decoding the token carries it on `exc.secrets` (P1-1) and
                # reaches the same revoke: both are scrubbed there, as Rejoin does (`gsd/rejoin.py#_exchange`).
                try:
                    sa_token = read_sa_token(session.token, cluster, source, timeout=settings.request_timeout_seconds)
                except LookupRefused as exc:
                    login.add_secrets(*exc.secrets)
                    raise
                login.add_secrets(sa_token.token)
        except LoginError as exc:
            which = f" against {exc.host}" if exc.host else ""
            if exc.bound:
                # THE PASSWORD WAS ON THE WIRE. The target evaluated it — refused it (401), answered
                # 500 (what the oauth-server says for every directory result but 48/49, a LOCKED
                # account's code 19 included), answered without a token — or may have: a read timeout
                # after the GET was written. Never sent again as this account, to this target or ANY
                # other, while it is this password (review of #295, P0-1; the operator's ruling on #325,
                # SPEC_S4c's orchestrator's notes, which reversed R2-1's per-target key — a locked
                # account's 500 cannot be told from a sick target's): re-entering #283's terminal answer
                # from a schedule is the lockout walk one layer up, and an in-memory "final" that any
                # shape change re-arms is not a stop. `AUTH_FAILED` is the refusal's word; the rest read
                # as failed. The Lease first, the process second (SPEC_S4c §3.3, step 5): a crash between the
                # two loses the cheap copy, never the durable one.
                code = "login-refused" if exc.outcome == AUTH_FAILED else "login-failed"
                if lease is not None:
                    lease.refuse(CredentialGate._target(cluster.api_url), digest, code)
                gate.refuse(cluster.api_url, account, password)
                raise LookupRefused(code, f"phase={exc.phase}{which}: {exc.message}",
                                    action=(f"the password for {account} was sent to {cluster.name} and no session came "
                                            f"back: rotate the fleet password Secret or correct ldapConnectionBootstrap, "
                                            f"or check the account is not locked — it is not sent again, to this or any "
                                            f"other cluster, while it is the same password"), spent=True) from exc
            if lease is not None:
                lease.complete()       # provably never written: the attempt's entry goes
            hint = ""
            if exc.phase == "tls":
                hint = (" — the stanza's CA must verify BOTH the API host and the OAuth route (the ingress CA, "
                        "which the API's bundle may not carry)")
            # Before the write — the socket never opened or the handshake failed: nothing was bound,
            # and the schedule may try again.
            raise LookupRefused("login-failed", f"phase={exc.phase}{which}: {exc.message}",
                                action=f"fix what detail names on the target or the stanza{hint}", spent=True) from exc
        secrets.append(sa_token.token)
        written = store(host_client, own_namespace, cluster, settings, sa_token, account=account) if write else None
    except LookupRefused as exc:
        # The boundary every refusal crosses: whatever a step quoted — a remote annotation, an API
        # server's echo — leaves here without the password, the session or the token in it (the
        # token a refused read carried rides `exc.secrets` already), and the poller's line is handed
        # the same values to strip again.
        exc.scrub(secrets)
        raise
    return LookupResult(cluster=cluster.name, account=account, sa_token=sa_token, secret=secret_name_for(cluster.name),
                        written=written, secrets=tuple(secrets))


__all__ = ["CODES", "LOOKUP_ATTEMPTS", "LOOKUP_WAIT_CAP", "CredentialGate", "LookupRefused", "LookupResult",
           "LookupSource", "SaToken", "declared_trust", "fleet_account", "fleet_password", "lookup", "read_sa_token",
           "store"]
