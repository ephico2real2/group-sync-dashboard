"""Read the oauth-server's AUDIT log and record who tried to log in — the second capture source.

WHAT THIS READS. Every OpenShift 4.11+ cluster writes the oauth-server's Kubernetes-audit-format
JSON to /var/log/oauth-server/audit.log on the control-plane node running it, one event per
request, at Metadata level, at every audit profile but `None`. A login attempt is the event whose
annotations carry BOTH `authentication.openshift.io/username` and
`authentication.openshift.io/decision` — allow, deny or error. No `spec.logLevel: Debug`, so no
OAuth roll and no login outage; and history as far back as the rotated files reach.
docs/DESIGN_login_capture.md has the measurement; docs/specs/SPEC_D1_audit_log_login_capture.md's
grounding note has the shapes, counted on the reference cluster's real log (49,360 records).

THREE KINDS, MEASURED. Of every annotated request that names a person, exactly three shapes are
logins and each is its own row of its kind:
  credential  POST /login[/<idp>]                              the interactive form
  cli         GET /oauth/authorize?client_id=openshift-challenging-client   `oc login`, curl basic auth
  session     GET /oauth/authorize with any OTHER client_id     an existing session re-authorising to
                                                                the console, this dashboard, GitOps
Consent (`/oauth/authorize/approve`) is a decision on a client, not a login, and is not a row. The
browser login's two annotated requests (POST /login, then GET /oauth/authorize) are two rows of two
kinds, not one login coalesced: the note measured 133 session re-authorisations up to 21 s after
their credential allow, so any coalescing window either hides real sessions or leaves spurious logins.

EVERY ATTEMPT IS A ROW, AND THE IDENTITY IS CLASSIFIED, NOT FILTERED. A failure against a name that
does not exist is still an attempt; the row carries `identity_match` — the configured identity
provider the username resolves to through a User's Identity, matched case-insensitively, because a
failed attempt can arrive in another case — or NULL, visibly unmatched. Only two things are never
rows: system accounts (`system:*`, `kube:admin`) and identities matching
`loginCapture.auditLog.ignoreIdentityPatterns` (default `ou=TrustedApplications`: an LDAP bind
service account's allows AND denies are not personnel events).

WHAT IT CANNOT SAY. `deny` carries no cause: the LDAP result codes exist only in the Debug pod log,
so a deny is `failed` and the row carries what the record has — the HTTP status (302 back to the
form for a browser failure, 401 for the CLI) and `responseStatus.message` when there is one
("Authentication failed, attempted: basic"). The identity provider is named on the path only for
`/login/<idp>`; otherwise it is resolved from the User's Identity, so a CLI `kubeadmin` row carries
`provider=developer` and the break-glass label can fire for it.

THE SHAPE OF ONE READ. Per node: list /var/log/oauth-server/, read each unread or partially read
file from its byte cursor (rotated files ascending by their stamp, then audit.log), parse whole
lines only, record, advance the cursor to the last newline consumed. A first sight is a BACKFILL
bounded by loginRetentionDays and by AUDIT_READ_MAX_BYTES per node per cycle, so a large history
drains over cycles on the poll thread instead of blocking it.

DE-DUPLICATION IS BY auditID, and by correspondence with the pod log: an audit credential event
matching a pod-log row for the same user and success class within CORRESPONDENCE_SECONDS is LINKED
to it (audit_id set on the existing row) rather than inserted beside it — the row keeps its cause.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs

from .config import ClusterConfig, Settings
from .kube import AUDIT_READ_MAX_BYTES, ClusterClient, ClusterError
from .loginlog import OUTCOME_FAILED, OUTCOME_PROVIDER_ERROR, OUTCOME_SUCCESS
from .storage import StorageBackend
from .timeutil import now_iso

log = logging.getLogger(__name__)

# The two annotation keys and three decisions, verbatim from openshift/oauth-server
# pkg/audit/annotation.go. The decision is the outcome; the username is the row's key.
USERNAME_ANNOTATION = "authentication.openshift.io/username"
DECISION_ANNOTATION = "authentication.openshift.io/decision"
DECISION_OUTCOME = {
    "allow": OUTCOME_SUCCESS,
    "deny": OUTCOME_FAILED,
    "error": OUTCOME_PROVIDER_ERROR,
}

KIND_CREDENTIAL = "credential"
KIND_CLI = "cli"
KIND_SESSION = "session"
KINDS = (KIND_CREDENTIAL, KIND_CLI, KIND_SESSION)
CHALLENGING_CLIENT = "openshift-challenging-client"

AUDIT_DIR = "oauth-server"
AUDIT_FILE = "audit.log"
# lumberjack's backup name: audit-<RFC3339 with dashes for colons>.<ms>.log — documented listing
# `audit-2021-03-09T00-12-19.834.log`. The stamp is the moment the file was CLOSED, so every
# event in it is older than the stamp; that is what makes the retention skip below sound.
ROTATED = re.compile(r"^audit-(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2})\.(\d+)\.log$")

# A pod-log row and an audit event for ONE login sit this close: measured 16 ms apart on the
# reference cluster — the same process stamps both, the audit record after the directory has
# answered, so no directory latency sits between them. A quarter second is fifteen times that.
# The closest same-user credential retry in the cluster's 49,360-record log was 3.6 s apart
# (133 pairs, none under 2 s), so the earlier 2 s window never reached a retry there; it is
# narrowed anyway so a busier cluster's retry cannot be linked to a previous attempt's row.
CORRESPONDENCE_SECONDS = 0.25

# A cursor row that marks a rotated file as skipped by retention: nothing to read, ever.
SKIPPED = -1

# FILE IDENTITY OVER HTTP. There is no inode through the node proxy, and the size cannot tell the
# file that was read from a new file under the same name once the new one has grown past the
# cursor (a resume would then start mid-line in the new file and lose its first bytes). So each
# cursor carries the sha256 of the file's first min(FINGERPRINT_BYTES, bytes consumed) bytes —
# at least one whole audit line, which holds a unique auditID — and a resume first re-reads
# exactly those bytes and compares. Filebeat's `file_identity.fingerprint` is the same idea.
# Costs one ~1 KiB request per in-progress file per cycle; complete rotated files pay nothing.
FINGERPRINT_BYTES = 1024

# The stamp format every login_event row uses (gsd/logincapture.py#event_dict). Fixed once.
STAMP = "%Y-%m-%dT%H:%M:%S.%fZ"

# Names that are never people. `kube:admin` is the installer's account; `system:` prefixes every
# built-in and service account identity.
SYSTEM_PREFIXES = ("system:",)
SYSTEM_NAMES = frozenset({"kube:admin"})

USER_AGENT_MAX = 120


@dataclass
class AuditLogin:
    """One login attempt as the audit log states it: no correlation, no inference."""

    audit_id: str
    user_name: str
    decision: str
    at: datetime
    kind: str
    request_path: str
    provider: str | None
    client_id: str | None
    response_code: int | None
    error_message: str | None
    user_agent: str | None


def parse_stamp(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def is_system_account(user_name: str) -> bool:
    name = user_name.strip()
    return name in SYSTEM_NAMES or name.startswith(SYSTEM_PREFIXES)


def parse_audit_line(line: str) -> AuditLogin | None:
    """One JSON line to a login attempt, or None for everything that is not one.

    Not one: unparsable JSON, a non-Event, a stage other than ResponseComplete (the policy omits no
    stages, so RequestReceived is written too, before the annotations exist), an event without
    BOTH annotations (the oauth-server audits every request; health probes, token exchanges and the
    login FORM's GET carry neither), a decision outside the three, a shape outside the three kinds
    (consent on /oauth/authorize/approve is a decision about a client, not a login), a system
    account, or a stamp that cannot be read. `user.username` is NOT consulted: on a login request
    it is system:anonymous (the request is what authenticates), which is why the annotation exists.

    The request path is kept WITHOUT its query string, and from the query exactly ONE parameter
    survives — `client_id`, the discriminator between a CLI login and a session re-authorisation.
    `redirect_uri`, `state`, the PKCE challenge and everything else are discarded: none is ours to
    store. A node-name prefix, as `oc adm node-logs --role` writes it, is tolerated.
    """
    start = line.find("{")
    if start < 0:
        return None
    try:
        event = json.loads(line[start:])
    except ValueError:
        return None
    if not isinstance(event, dict) or event.get("kind") != "Event":
        return None
    if event.get("stage") != "ResponseComplete":
        return None
    annotations = event.get("annotations") or {}
    user = annotations.get(USERNAME_ANNOTATION)
    decision = annotations.get(DECISION_ANNOTATION)
    if not user or decision not in DECISION_OUTCOME:
        return None
    user = str(user)
    if is_system_account(user):
        return None
    uri = str(event.get("requestURI") or "")
    path, _, query = uri.partition("?")
    verb = str(event.get("verb") or "").lower()
    kind: str | None = None
    provider: str | None = None
    client_id: str | None = None
    if verb == "post" and (path == "/login" or re.fullmatch(r"/login/[^/]+", path)):
        kind = KIND_CREDENTIAL
        if path.startswith("/login/") and len(path) > len("/login/"):
            provider = path[len("/login/"):].split("/", 1)[0] or None
    elif verb == "get" and path == "/oauth/authorize":
        client_id = (parse_qs(query).get("client_id") or [None])[0] or None
        if not client_id:
            # An authorize request that names no client is not a login to anything; every one of
            # the 259 username-annotated authorize records measured on the reference cluster named
            # its client, so this is a malformed request, not a fourth shape.
            return None
        kind = KIND_CLI if client_id == CHALLENGING_CLIENT else KIND_SESSION
    if kind is None:
        return None
    at = parse_stamp(event.get("stageTimestamp")) or parse_stamp(event.get("requestReceivedTimestamp"))
    audit_id = event.get("auditID")
    if at is None or not audit_id:
        return None
    status = event.get("responseStatus") or {}
    code = status.get("code")
    message = status.get("message")
    agent = event.get("userAgent")
    return AuditLogin(
        audit_id=str(audit_id), user_name=user, decision=decision, at=at, kind=kind,
        request_path=path, provider=provider, client_id=client_id,
        response_code=int(code) if isinstance(code, int) else None,
        error_message=str(message)[:200] if message else None,
        user_agent=str(agent)[:USER_AGENT_MAX] if agent else None,
    )


def decode_identity_suffix(identity_name: str) -> str:
    """The part of an Identity name after the provider, decoded when it is base64url (an LDAP
    provider encodes the DN that way); otherwise as it is (an HTPasswd provider keeps the username)."""
    suffix = identity_name.split(":", 1)[1] if ":" in identity_name else identity_name
    padded = suffix + "=" * (-len(suffix) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return suffix
    # A DN decodes to printable text with an '=' in it; anything else was not base64 to begin with.
    return decoded if decoded.isprintable() and "=" in decoded else suffix


def identity_match_for(
    user_name: str, identities: list[str], configured_providers: set[str] | frozenset[str] | None,
) -> str | None:
    """The configured provider a login's username resolves to through a User's Identity names, or
    None. Case-insensitive on the username — the audit log records what was TYPED, and a failed
    attempt for `LATEEF.O` belongs to the person `lateef.o` (grounding note). `identities` are the
    User's Identity names, `<provider>:<providerUserName>`; the first whose provider is configured
    wins, in the order given (sorted by the poller). `configured_providers` is None when the
    OAuth CR could not be read — then any provider an Identity names counts, and the loop says so
    at WARNING — and a SET otherwise, an empty one meaning the CR lists no provider at all, so no
    Identity can be current and nothing matches (Codex, review D1)."""
    del user_name  # the caller already selected the User whose identities these are
    for identity in identities:
        provider = identity.split(":", 1)[0]
        if configured_providers is None or provider in configured_providers:
            return provider
    return None


def ignored_identity(
    identities: list[str], patterns: tuple[str, ...], plain_suffix_providers: tuple[str, ...] = (),
) -> bool:
    """Whether any of a User's identities matches an ignore pattern — case-insensitively, against
    the decoded suffix of the Identity name (the DN for an LDAP provider). Measured: the LDAP bind
    service account's Identity decodes to `cn=…,ou=TrustedApplications,dc=…`, so the OU is the
    data-derived discriminator. An identity of a provider in `plain_suffix_providers` (the
    HTPasswd providers, `loginCapture.htpasswdProviders`) is compared as written and never
    decoded: its suffix is the bare username, and a username that happens to be valid base64url
    of a DN fragment must not be dropped for what it decodes to (Codex, review D1)."""
    if not patterns:
        return False
    lowered = [p.lower() for p in patterns if p]
    for identity in identities:
        provider, _, suffix = identity.partition(":")
        text = (suffix if provider in plain_suffix_providers else decode_identity_suffix(identity)).lower()
        if any(p in text for p in lowered):
            return True
    return False


class IdentityIndex:
    """The join from a typed username to a User's identities, case-insensitive, built once per
    capture pass from the store's last User read (rbac.users). Empty when the Users tab has no
    source — then every row is `identity_match=None`, which the log says once."""

    def __init__(self, user_identities: dict[str, list[str]], configured: set[str] | None,
                 ignore_patterns: tuple[str, ...], plain_suffix_providers: tuple[str, ...] = ()):
        self._by_lower: dict[str, list[str]] = {}
        for name, identities in user_identities.items():
            self._by_lower.setdefault(name.lower(), identities)
        self.configured = configured
        self.ignore_patterns = ignore_patterns
        self.plain_suffix_providers = plain_suffix_providers

    def identities(self, user_name: str) -> list[str]:
        return self._by_lower.get(user_name.lower(), [])

    def match(self, user_name: str) -> str | None:
        return identity_match_for(user_name, self.identities(user_name), self.configured)

    def ignored(self, user_name: str) -> bool:
        return ignored_identity(self.identities(user_name), self.ignore_patterns,
                                self.plain_suffix_providers)


def audit_event_dict(login: AuditLogin, node: str, observed_at: str, index: IdentityIndex | None = None) -> dict:
    """The store row for an audit login — gsd/logincapture.py#event_dict's shape, plus the columns
    this source owns. `pod_name` carries the NODE: it is "the unit of log this was read from" in
    the dedup key, and a node is that unit here. The provider is the path's when the path names
    one, else the identity match (a CLI login names none, and its User's Identity does)."""
    match = index.match(login.user_name) if index is not None else None
    provider = login.provider or match
    reason = "" if login.decision == "allow" else (
        f" — {login.error_message}" if login.error_message else " (the audit log records no cause)")
    target = login.client_id if login.kind != KIND_CREDENTIAL else login.request_path
    return {
        "pod_name": node,
        "user_name": login.user_name,
        "outcome": DECISION_OUTCOME[login.decision],
        "at": login.at.strftime(STAMP),
        "provider": provider,
        "ldap_result_code": None,
        "detail": f"audit: {login.kind} {login.decision} via {target or '?'}{reason}",
        "observed_at": observed_at,
        "source": "audit-log",
        "audit_id": login.audit_id,
        "kind": login.kind,
        "client_id": login.client_id,
        "identity_match": match,
        "status_code": login.response_code,
        "error_message": login.error_message,
        "user_agent": login.user_agent,
    }


def fingerprint(head: bytes) -> tuple[str, int] | None:
    """(sha256 hex, length) of a file's first bytes, capped at FINGERPRINT_BYTES; None for none."""
    head = head[:FINGERPRINT_BYTES]
    if not head:
        return None
    return hashlib.sha256(head).hexdigest(), len(head)


def rotated_at(name: str) -> datetime | None:
    """When a rotated file was closed, from its name; None for audit.log or an unexpected name."""
    m = ROTATED.match(name)
    if not m:
        return None
    day, hh, mm, ss, frac = m.groups()
    try:
        return datetime.fromisoformat(f"{day}T{hh}:{mm}:{ss}.{frac[:6]:0<6}+00:00")
    except ValueError:
        return None


def complete_lines(data: bytes) -> tuple[list[str], int]:
    """Whole lines from a byte read, and how many bytes they occupy.

    The last line of a live file is usually half-written; it is left for the next read by not
    counting it, so the cursor never lands mid-JSON. errors="replace" cannot corrupt a kept line:
    the only place a multi-byte character can be split is the end, and the end is not kept.
    """
    cut = data.rfind(b"\n")
    if cut < 0:
        return [], 0
    return data[:cut].decode("utf-8", errors="replace").split("\n"), cut + 1


def _configured_providers(client: ClusterClient, cluster: ClusterConfig, settings: Settings) -> set[str] | None:
    """The providers a username may resolve to: the values list when set, else every identity
    provider on the OAuth CR, read each pass. None when the CR cannot be read ('no narrowing',
    said at WARNING); an empty set when it was read and lists none."""
    if settings.login_capture_audit_providers:
        return set(settings.login_capture_audit_providers)
    fetch = getattr(client, "fetch_oauth_providers", None)
    if fetch is None:
        return None
    try:
        names = fetch()
    except ClusterError as exc:
        names = None
        log.debug("%s: could not read the OAuth CR's providers (%s)", cluster.name, exc.message)
    if names is None:
        # The chart grants `get oauths` (templates/rbac.yaml), so this is an install that removed
        # it. Said at WARNING, once per cycle: identity_match then means "some provider", not
        # "one the OAuth CR still lists", which is weaker than the row's column name promises.
        log.warning("%s: the OAuth CR's identity providers could not be read; identity_match is "
                    "computed against every provider an Identity names, not the CR's list "
                    "(loginCapture.auditLog.providers pins it)", cluster.name)
        return None
    return set(names)


def _hand_over(store, client, cluster, node, order, cursors, offset, head, cur) -> None:
    """audit.log was rotated: the bytes read so far now live under the newest rotated name that
    has no cursor yet. Hand the cursor (and fingerprint) to it — but only after the fingerprint
    confirms that file starts with the same bytes; otherwise leave it to be read from 0, where
    auditID makes the re-read free. audit.log itself starts again at 0. The local `cursors`
    view is updated too, so the rotated file is not visited as fresh later this same cycle."""
    fresh = [n for n in order if n != AUDIT_FILE and n not in cursors]
    target = fresh[-1] if fresh else None
    if target is not None and head is not None:
        probe = client.fetch_node_log_file(node, f"{AUDIT_DIR}/{target}", offset=0,
                                           max_bytes=head[1])
        if probe is None or fingerprint(probe.data[:head[1]]) != head:
            log.warning("%s: %s: audit.log rotated but %s does not start with the bytes read "
                        "from it; it will be read from 0", cluster.name, node, target)
            target = None
    if target is not None:
        settled = (cur or {}).get("settled_through")
        store.set_audit_cursor(cluster.name, node, target, offset, settled, now_iso(),
                               complete=False, head=head)
        cursors[target] = {"byte_offset": offset, "head": head, "settled_through": settled,
                           "complete": False}
    store.set_audit_cursor(cluster.name, node, AUDIT_FILE, 0, None, now_iso(), complete=False)
    cursors[AUDIT_FILE] = {"byte_offset": 0, "head": None, "settled_through": None,
                           "complete": False}
    log.info("%s: %s: audit.log rotated at byte %d; cursor %s", cluster.name, node, offset,
             f"handed to {target}" if target else "restarted at 0 (no rotated file took it)")


def capture_once(
    store: StorageBackend,
    cluster: ClusterConfig,
    settings: Settings,
    elector=None,
    timeout: float = 15.0,
    signals=None,
) -> int:
    """One audit-log capture pass over one cluster. Returns rows recorded. NEVER raises for a
    cluster problem — the same contract, and the same leadership recheck before every write, as
    gsd/logincapture.py#capture_once, which dispatches here on loginCapture.source=audit-log."""
    from .logincapture import _prune  # here, not at module level: logincapture imports this module

    client = ClusterClient(cluster, timeout=timeout)
    nodes: list[str] | None
    if settings.login_capture_audit_node_names:
        nodes = list(settings.login_capture_audit_node_names)
    else:
        try:
            nodes = client.fetch_nodes(settings.login_capture_audit_node_selector)
        except ClusterError as exc:
            log.warning("%s: audit-log capture could not list nodes: %s — group data is "
                        "unaffected", cluster.name, exc.message)
            return 0
        if nodes is None:
            log.warning("%s: audit-log capture is enabled but not permitted to list nodes, so no "
                        "logins will be recorded until the grant is applied (or pin "
                        "loginCapture.auditLog.nodeNames)", cluster.name)
            return 0
    if not nodes:
        log.info("%s: no node matched %r; audit-log capture has nothing to read",
                 cluster.name, settings.login_capture_audit_node_selector)
        return 0

    cutoff: datetime | None = None
    if settings.login_retention_days > 0:
        cutoff = datetime.now(UTC) - timedelta(days=settings.login_retention_days)

    identities = store.user_identities(cluster.name)
    index = IdentityIndex(identities, _configured_providers(client, cluster, settings),
                          tuple(settings.login_capture_audit_ignore_identity_patterns),
                          tuple(settings.login_capture_htpasswd_providers))
    if not identities:
        log.info("%s: no User records to resolve identities against (rbac.users off, or no poll "
                 "yet); audit rows are recorded with identity_match unset", cluster.name)

    recorded = 0
    read_ok = False
    unmatched: dict[str, int] = {}
    for node in nodes:
        names = client.list_node_log_files(node, AUDIT_DIR)
        if names is None:
            continue
        files = [n for n in names if n == AUDIT_FILE or ROTATED.match(n)]
        if not files:
            # The directory exists and holds nothing audit-shaped: the audit profile is None,
            # or this node never ran the oauth-server. Not "nobody logged in".
            log.info("%s: %s has no audit files under /var/log/%s — is the cluster's audit "
                     "profile None? (apiserver.config.openshift.io/cluster spec.audit.profile)",
                     cluster.name, node, AUDIT_DIR)
            continue
        cursors = store.audit_cursors(cluster.name, node)
        order = sorted((n for n in files if n != AUDIT_FILE),
                       key=lambda n: rotated_at(n) or datetime.min.replace(tzinfo=UTC))
        if AUDIT_FILE in files:
            # First sight reads oldest-first so settled_through only ever advances. Once
            # audit.log has a cursor it goes FIRST: its rotation must be noticed — and its cursor
            # handed to the newest rotated file — before that rotated file is visited as a fresh
            # one and re-read from byte 0. Live bytes before backfill is the better budget order too.
            if cursors.get(AUDIT_FILE, {}).get("byte_offset", 0) > 0:
                order.insert(0, AUDIT_FILE)
            else:
                order.append(AUDIT_FILE)
        budget = AUDIT_READ_MAX_BYTES
        first_sight = not cursors
        for name in order:
            if budget <= 0:
                log.debug("%s: %s: byte budget spent; %s waits for the next cycle",
                          cluster.name, node, name)
                break
            cur = cursors.get(name)
            if cur is not None and (cur["byte_offset"] == SKIPPED or cur["complete"]):
                continue
            offset = cur["byte_offset"] if cur is not None else 0
            head = cur["head"] if cur is not None else None
            if cur is None and name != AUDIT_FILE and cutoff is not None:
                closed = rotated_at(name)
                if closed is not None and closed < cutoff:
                    # Older than retention when it was closed, so everything inside it is too.
                    store.set_audit_cursor(cluster.name, node, name, SKIPPED, None, now_iso(),
                                           complete=True)
                    continue
            path = f"{AUDIT_DIR}/{name}"
            same_file: bool | None = None
            if offset > 0 and head is not None:
                probe = client.fetch_node_log_file(node, path, offset=0, max_bytes=head[1])
                if probe is None:
                    continue
                # Deliberately not `read_ok = True` here: a probe that succeeds while every body
                # read fails must not advance the last-read stamp the stalled alert watches.
                same_file = fingerprint(probe.data[:head[1]]) == head
            if same_file is False:
                read = None
            else:
                read = client.fetch_node_log_file(node, path, offset=offset, max_bytes=budget)
                if read is None:
                    continue
                read_ok = True
            if read is None or read.rotated:
                # The file under this name is not the one the cursor was read from: its head
                # changed, or it is shorter than the cursor (kube.py#fetch_node_log_file).
                if name == AUDIT_FILE:
                    _hand_over(store, client, cluster, node, order, cursors, offset, head, cur)
                else:
                    log.warning("%s: %s: rotated file %s is not the file its cursor was read "
                                "from; re-reading from 0 (auditID makes that free)",
                                cluster.name, node, name)
                    store.set_audit_cursor(cluster.name, node, name, 0, None, now_iso(),
                                           complete=False)
                offset, head, cur = 0, None, None
                read = client.fetch_node_log_file(node, path, offset=0, max_bytes=budget)
                if read is None:
                    continue
                read_ok = True
            lines, consumed = complete_lines(read.data)
            if name != AUDIT_FILE and not read.truncated and consumed < len(read.data):
                # A ROTATED file is closed: nothing will ever append the newline its last line
                # lacks (a crash mid-write leaves one). Take the tail as the final line — the
                # parser rejects it if it is not whole JSON — or the cursor would sit on it forever.
                lines.append(read.data[consumed:].decode("utf-8", errors="replace"))
                consumed = len(read.data)
            if offset == 0 and consumed:
                head = fingerprint(read.data[:consumed])
            budget -= len(read.data)
            parsed = [l for l in (parse_audit_line(x) for x in lines) if l is not None]
            in_window = [l for l in parsed if cutoff is None or l.at >= cutoff]
            kept = [l for l in in_window if not index.ignored(l.user_name)]
            log.debug("%s: %s: %s read %d byte(s) from offset %d%s — %d line(s), %d login "
                      "event(s), %d inside retention, %d after the identity filter",
                      cluster.name, node, name, len(read.data), offset,
                      " (first sight: backfill)" if first_sight else "",
                      len(lines), len(parsed), len(in_window), len(kept))
            if lines and not parsed and name == AUDIT_FILE:
                log.debug("%s: %s: %d audit line(s) and no login attempt in any of them — either "
                          "nobody logged in, or this oauth-server build annotates nothing",
                          cluster.name, node, len(lines))
            observed_at = now_iso()
            events = [audit_event_dict(l, node, observed_at, index) for l in kept]
            for e in events:
                if e["identity_match"] is None:
                    unmatched[e["outcome"]] = unmatched.get(e["outcome"], 0) + 1

            # THE RECHECK. Everything above is reads; everything below writes.
            if elector is not None and not elector.is_leader:
                log.info("%s: lost leadership while reading %s on %s — discarding %d event(s)",
                         cluster.name, name, node, len(events))
                return recorded
            inserted, linked = (store.record_audit_login_events(
                cluster.name, events, CORRESPONDENCE_SECONDS) if events else (0, 0))
            recorded += inserted
            settled = max((l.at for l in parsed), default=None)
            complete = name != AUDIT_FILE and not read.truncated and consumed == len(read.data)
            store.set_audit_cursor(
                cluster.name, node, name, offset + consumed,
                settled.strftime(STAMP) if settled else (cur or {}).get("settled_through"),
                observed_at, complete=complete, head=head,
            )
            if inserted or linked:
                log.info("%s: recorded %d login attempt(s) from the audit log on %s (%s)%s",
                         cluster.name, inserted, node, name,
                         f", linked {linked} to pod-log rows" if linked else "")
        if elector is None or elector.is_leader:
            dropped = store.prune_audit_cursors(cluster.name, node, files)
            if dropped:
                log.info("%s: %s: forgot %d cursor(s) for audit files that rotated away",
                         cluster.name, node, dropped)

    if signals is not None and unmatched:
        note = getattr(signals, "note_audit_unmatched", None)
        if note is not None:
            for outcome, count in unmatched.items():
                note(cluster.name, outcome, count)
    if not read_ok:
        log.warning("%s: audit-log capture read none of the %d node(s) this cycle; the last-read "
                    "stamp is deliberately not advanced", cluster.name, len(nodes))
        return recorded
    if elector is not None and not elector.is_leader:
        return recorded
    store.record_login_read(cluster.name, now_iso())
    _prune(store, cluster, settings, elector, signals)
    return recorded
