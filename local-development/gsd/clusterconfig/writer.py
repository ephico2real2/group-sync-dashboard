"""The Cluster Configurations tab's writes (docs/specs/SPEC_S2_cluster_configurations_tab.md, C2–C5):
create a labelled Secret, rotate its bearer token in place, delete it, and test a connection before
writing anything.

Every write goes through the HOST cluster's client into the pod's own namespace and touches only a
Secret carrying our label — the app checks the label itself before an update or a delete, because
RBAC cannot scope a verb by label. The request is validated by the SAME parser discovery runs
(`parse_secret` on the object about to be written), so a request this module accepts is a Secret the
next discovery accepts, byte for byte. The credential is never logged here: a finding names the key,
the audit line names the person, the verb and the Secret — in #245's `event-name key=value` shape and
through its emit helper, so the write path and the discovery path speak one vocabulary and the
credential in play is handed to the one place that redacts.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import re
from dataclasses import dataclass, field

from ..config import ClusterConfig
from ..config import CONNECTION_KEYS, CREDENTIAL_LOOKUP, CREDENTIAL_SELF_LOGIN
from ..kube import AUTH_FAILED, FORBIDDEN, UNREACHABLE, ClusterClient, ClusterError, redact_text
from . import SECRET_TYPE_CLUSTER, SECRET_TYPE_LABEL
from .events import event
from .parser import Finding, parse_secret

log = logging.getLogger(__name__)

SECRET_NAME_PREFIX = "gsd-cluster-"
MANAGED_BY_ANNOTATION = "groupsync-dashboard.io/managed-by"
MANAGED_BY_UI = "ui"
#: The saTokenLookup lookup (SPEC_S4b): the stanza key in kebab case, so `saTokenLookup: true` and
#: `managed-by: sa-token-lookup` read as one thing. Says WHO wrote the Secret; `token-source` says how.
MANAGED_BY_LOOKUP = "sa-token-lookup"
#: PROVENANCE, NOT CONFIGURATION (SPEC_S3 §5.1). A bearer token is opaque: nothing in it says where it
#: came from or what to rotate when it must change. These three answer that, on the tab and in a
#: support ticket. They are ignored by the parser and by the poll — they exist for the human, and for
#: S3d, which may only refresh or delete what this dashboard made (§8.1).
TOKEN_SOURCE_ANNOTATION = "groupsync-dashboard.io/token-source"
SOURCE_NAMESPACE_ANNOTATION = "groupsync-dashboard.io/source-namespace"
SOURCE_SERVICE_ACCOUNT_ANNOTATION = "groupsync-dashboard.io/source-service-account"
#: The account the lookup logged in AS (SPEC_S4b). A Secret that declared the mode is updated in
#: place and its `ldapConnectionBootstrap` must leave `config` with the mode key, so this is where
#: the per-cluster account survives for #285's re-login; written on the values path too.
LOOKUP_ACCOUNT_ANNOTATION = "groupsync-dashboard.io/lookup-account"
#: How the credential was obtained. `managed-by` says WHO created the Secret; this says HOW the
#: credential in it was got — the two are orthogonal and a retriever sets both.
#:
#: NOT A SECOND VOCABULARY. The value IS the `credential_kind` the declaring mode resolves to, so the
#: chain is one thing end to end: `saTokenLookup: true` -> `ClusterConfig.credential_kind` ->
#: `"remote-lookup"` -> this annotation. Defining it again here would be two constants that happen to
#: be equal today, and the tab would disagree with the Secret the first time one of them moved.
#: The two differ in what they LEAVE BEHIND, which is why a reader of the Secret needs to be told
#: which one made it:
#:   lookup     — log in as the fleet account, read the target ServiceAccount's PERMANENT token and
#:                store it. The credential outlives the login; the tab says `expires: current`,
#:                because it is invalidated by deleting its Secret rather than by a clock (#248).
#:   self-login — no retrieval at all: the dashboard polls AS the LDAP account, on its own session.
#:                The credential IS the login, so it expires on the target's own terms (§3.2,
#:                `accessTokenMaxAgeSeconds`, 24 h by default), the tab shows a real date, and
#:                renewal is not optional. It is also the mode where nothing long-lived is at rest.
TOKEN_SOURCE_LOOKUP = CREDENTIAL_LOOKUP          # saTokenLookup
TOKEN_SOURCE_SELF_LOGIN = CREDENTIAL_SELF_LOGIN  # userSelfLogin
LABEL_DOMAIN = "groupsync-dashboard.io/"
TLS_MODES = ("caData", "trustedBundle", "insecure")
# Kubernetes' label syntax (metav1 validation): a key is an optional DNS-subdomain prefix (≤ 253) and a
# `/`, then a name of ≤ 63 characters `[A-Za-z0-9]([-A-Za-z0-9_.]*[A-Za-z0-9])?`; a value is empty or the
# same shape, ≤ 63. Refused HERE, naming the key, rather than sent and answered 422 → 502 by the API
# server (round 2, Grok C8/C16: a newline or a 64-character key reached the wire).
_LABEL_NAME = re.compile(r"^[A-Za-z0-9]([-A-Za-z0-9_.]{0,61}[A-Za-z0-9])?$")
_LABEL_PREFIX = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$")
OAUTH_NOT_BUILT = "the password-for-token exchange is #119 P2, not built yet"
MIN_TOKEN_LENGTH = 8   # the redactor's floor (kube.redact_text); no cluster mints a shorter bearer


class WriteRefused(Exception):
    """A request the contract refuses before any write: `code` is a finding code (or `duplicate-cluster-name`,
    `not-a-secret-cluster`, `not-our-secret`, `secret-exists`, `secret-changed`, `label-invalid`,
    `config-not-json`), `detail` the sentence."""

    def __init__(self, code: str, detail: str, *, conflict: bool = False):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail, self.conflict = code, detail, conflict


class WriteFailed(Exception):
    """The API server refused or could not be reached: `outcome` is the ClusterError's word."""

    def __init__(self, outcome: str, message: str):
        super().__init__(f"{outcome}: {message}")
        self.outcome, self.message = outcome, message


@dataclass(frozen=True)
class CreateRequest:
    name: str
    server: str
    credential_kind: str          # bearerToken | oauth
    token: str | None = field(default=None, repr=False)
    tls_mode: str = "trustedBundle"
    ca_data: str | None = field(default=None, repr=False)   # base64 PEM, as the Secret carries it
    visibility: str = "self-only"
    identity: str = "none"
    labels: dict[str, str] = field(default_factory=dict)
    #: Written as the WORD "true"/"false", which is how the parser reads it back
    #: (`data.enabled` unset means true; anything but those two words is a finding). Default true:
    #: a cluster is created because someone means to poll it.
    enabled: bool = True
    #: Who created the Secret. `ui` for the tab's form; a retriever names itself, so a machine-written
    #: Secret does not claim a person made it.
    managed_by: str = MANAGED_BY_UI
    #: Provenance — the rotation address. Omitted entirely when unset, so a hand-made Secret and a
    #: UI-written one carry no empty markers for S3d to misread as ownership.
    token_source: str | None = None
    source_namespace: str | None = None
    source_service_account: str | None = None
    lookup_account: str | None = None


def secret_name_for(cluster: str) -> str:
    return f"{SECRET_NAME_PREFIX}{cluster}"


def secret_object(req: CreateRequest, namespace: str, *, redact: bool = False) -> dict:
    """The Secret the API writes (C2) — and, with `redact`, the page's "as GitOps would write it" twin:
    the same object with the credential as `<redacted>`. A test holds the two equal field for field."""
    tls: dict = {"insecure": req.tls_mode == "insecure"}
    if req.tls_mode == "caData":
        tls["caData"] = "<redacted>" if redact else (req.ca_data or "")
    config: dict = {"tlsClientConfig": tls}
    if req.credential_kind == "oauth":
        config["oauth"] = {"username": "<redacted>", "password": "<redacted>"}
    else:
        config["bearerToken"] = "<redacted>" if redact else (req.token or "").strip()   # as validate and rotate read it
    # THE TYPE LABEL IS STAMPED LAST, so no caller-supplied label can replace it (SPEC_S4b, the
    # operator's requirement): `validate()` refuses the app's prefix, but this function has callers
    # that do not validate — the lookup, and #293's ConfigMap feed whose labels someone else wrote —
    # and a Secret without `secret-type: cluster` is one discovery cannot see. Byte-identical for
    # every input `validate()` accepts.
    labels = {**{str(k): str(v) for k, v in (req.labels or {}).items()}, SECRET_TYPE_LABEL: SECRET_TYPE_CLUSTER}
    # Built the way `labels` is, rather than a fixed dict: a retriever records where it got the token
    # (SPEC_S3 §5.1). An unset marker is OMITTED, never written empty — S3d reads these to decide what
    # it owns, and an empty string is not an answer.
    annotations = {MANAGED_BY_ANNOTATION: req.managed_by}
    for key, value in ((TOKEN_SOURCE_ANNOTATION, req.token_source),
                       (SOURCE_NAMESPACE_ANNOTATION, req.source_namespace),
                       (SOURCE_SERVICE_ACCOUNT_ANNOTATION, req.source_service_account),
                       (LOOKUP_ACCOUNT_ANNOTATION, req.lookup_account)):
        if value:
            annotations[key] = str(value)
    return {
        "apiVersion": "v1", "kind": "Secret",
        "metadata": {"name": secret_name_for(req.name), "namespace": namespace, "labels": labels,
                     "annotations": annotations},
        "type": "Opaque",
        # Compact separators: the page's twin is JSON.stringify under a `|-` block, and the promise is that
        # the two Secrets are equal BYTE FOR BYTE, `config` included — not merely equal once parsed.
        "stringData": {"name": req.name, "server": req.server, "config": json.dumps(config, separators=(",", ":")),
                       "visibility": req.visibility, "identity": req.identity,
                       "enabled": "true" if req.enabled else "false"},
    }


def validate(req: CreateRequest, namespace: str, *, host_name: str | None,
             taken: dict[str, str]) -> ClusterConfig:
    """The contract's refusals (C2), in order, before any write. `taken` maps every cluster id the
    instance already knows to its source (values | secret:<name>). Returns the ClusterConfig the
    written Secret would parse to."""
    if req.credential_kind == "oauth":
        raise WriteRefused("oauth-exchange-not-built", OAUTH_NOT_BUILT)
    if req.credential_kind != "bearerToken":
        raise WriteRefused("credential-missing", "credential.kind must be bearerToken")
    if not (req.token or "").strip():
        raise WriteRefused("credential-missing", "a bearer token is required")
    if len(req.token.strip()) < MIN_TOKEN_LENGTH:
        # No cluster mints a bearer token this short (a ServiceAccount token is a JWT, an OpenShift
        # OAuth token `sha256~…`), so it is a paste error — and it is also the redactor's floor, below
        # which an echoed value could not be scrubbed without wiping the sentence (round 2, Codex C7).
        raise WriteRefused("credential-missing", f"a bearer token is at least {MIN_TOKEN_LENGTH} characters; this one looks truncated")
    if req.tls_mode not in TLS_MODES:
        raise WriteRefused("unsupported-config-key", f"tls.mode must be one of {', '.join(TLS_MODES)}")
    if req.tls_mode == "caData":
        if not req.ca_data:
            raise WriteRefused("ca-data-invalid", "tls.mode caData needs tls.caData (a base64 PEM bundle)")
        try:
            base64.b64decode(req.ca_data, validate=True)
        except (binascii.Error, ValueError):
            raise WriteRefused("ca-data-invalid", "tls.caData must be a base64 PEM bundle") from None
    for key, value in (req.labels or {}).items():
        key, value = str(key), str(value)
        if key.startswith(LABEL_DOMAIN):
            raise WriteRefused("unsupported-config-key", f"label {key}: the {LABEL_DOMAIN} prefix is the app's")
        prefix, _, name = key.rpartition("/")
        if key.count("/") > 1 or not _LABEL_NAME.match(name) or (prefix and (len(prefix) > 253 or not _LABEL_PREFIX.match(prefix))):
            raise WriteRefused("label-invalid", f"label key {key!r}: an optional DNS prefix and a slash, then ≤ 63 "
                                                "characters of letters, digits, '-', '_' or '.', starting and ending alphanumeric")
        if value and not _LABEL_NAME.match(value):
            raise WriteRefused("label-invalid", f"label {key}: the value must be empty or ≤ 63 characters of letters, "
                                                "digits, '-', '_' or '.', starting and ending alphanumeric")
    parsed = parse_secret(secret_object(req, namespace), host_name=host_name)
    if isinstance(parsed, Finding):
        raise WriteRefused(parsed.code, parsed.detail)
    if parsed.name in taken:
        raise WriteRefused("duplicate-cluster-name", f"{parsed.name} is already declared by {taken[parsed.name]}", conflict=True)
    return parsed


def _path(namespace: str, name: str | None = None) -> str:
    base = f"/api/v1/namespaces/{namespace}/secrets"
    return f"{base}/{name}" if name else base


def _labelled(obj: dict) -> bool:
    labels = (obj.get("metadata") or {}).get("labels") or {}
    return labels.get(SECRET_TYPE_LABEL) == SECRET_TYPE_CLUSTER


def _scrub(text: str, *secrets: str | None) -> str:
    """The request's own credential, in every spelling, out of a sentence about to leave this module —
    `kube.redact_text`, the one redactor. The host client cannot recognise the token a caller asked us
    to write, so the writer names it (and, on rotate, the base64 `data.config` blob that encodes it),
    both to `_send` — which redacts BEFORE truncating — and here, for the connection test's `error`
    (review of #237: Codex C2 measured the sentinel in a 502; round 2, Codex C7 and Grok C7 the
    escaped spellings and the truncation boundary)."""
    return redact_text(text, *secrets)


def _failed(exc: ClusterError, *secrets: str | None) -> WriteFailed:
    if exc.outcome == FORBIDDEN:
        return WriteFailed(FORBIDDEN, "the ServiceAccount may not write Secrets here — the chart's "
                                     "clusterConfig.secrets.writes switch renders the grant")
    return WriteFailed(exc.outcome, _scrub(exc.message, *secrets))


def create(host_client: ClusterClient, namespace: str, req: CreateRequest, *, host_name: str | None,
           taken: dict[str, str], viewer: str) -> str:
    """C2: validate, refuse an existing Secret of that name, POST, one audit line. Returns the Secret's name."""
    validate(req, namespace, host_name=host_name, taken=taken)
    obj = secret_object(req, namespace)
    name = obj["metadata"]["name"]
    with host_client._client() as client:
        try:
            host_client._get(client, _path(namespace, name), {})
        except ClusterError as exc:
            if not exc.message.startswith("HTTP 404"):
                raise _failed(exc, req.token) from exc
        else:
            raise WriteRefused("secret-exists", f"Secret {name} already exists in {namespace}", conflict=True)
        try:
            host_client._send(client, "POST", _path(namespace), json=obj, secrets=(req.token, obj["stringData"]["config"]))
        except ClusterError as exc:
            # Two creates that both passed the 404 probe: the second is the API server's 409, the same
            # refusal the probe would have given (round 2, OB2 C16 — it read "unreachable: HTTP 409 …").
            if exc.message.startswith("HTTP 409"):
                raise WriteRefused("secret-exists", f"Secret {name} already exists in {namespace}", conflict=True) from exc
            raise _failed(exc, req.token, obj["stringData"]["config"]) from exc
    event(log, logging.INFO, "cluster-secret-created", secret=name, namespace=namespace, cluster=req.name,
          by=viewer, secrets=(req.token,))
    return name


def _read_ours(host_client: ClusterClient, client, namespace: str, name: str) -> dict:
    try:
        obj = host_client._get(client, _path(namespace, name), {})
    except ClusterError as exc:
        if exc.message.startswith("HTTP 404"):
            raise WriteRefused("not-our-secret", f"Secret {name} is not in {namespace}") from exc
        raise _failed(exc) from exc
    if not _labelled(obj):
        # Never touched: the grant covers every Secret in the namespace, the app's own rule is the label.
        raise WriteRefused("not-our-secret", f"Secret {name} does not carry {SECRET_TYPE_LABEL}={SECRET_TYPE_CLUSTER}", conflict=True)
    return obj


def rotate(host_client: ClusterClient, namespace: str, name: str, token: str, *, viewer: str, cluster: str) -> None:
    """C3: replace `config.bearerToken` in place, every other key kept; the old token is gone on the write."""
    if not (token or "").strip():
        raise WriteRefused("credential-missing", "a bearer token is required")
    if len(token.strip()) < MIN_TOKEN_LENGTH:
        raise WriteRefused("credential-missing", f"a bearer token is at least {MIN_TOKEN_LENGTH} characters; this one looks truncated")
    with host_client._client() as client:
        obj = _read_ours(host_client, client, namespace, name)
        data = obj.get("data") or {}
        # The API server always answers with `data` (base64), whatever shape wrote the Secret. A config
        # that does not decode to a JSON object is REFUSED, not replaced: writing `{"bearerToken": …}`
        # over it would silently drop the cluster's tlsClientConfig — a caData cluster would come back
        # trusting the default bundle — and a Secret in that state is a `config-not-json` finding the
        # reader already names, so the person can see what to fix. Discovery lists only parseable
        # Secrets, so this is reached only when the Secret changed under the tab.
        try:
            config = json.loads(base64.b64decode(data.get("config") or "", validate=True).decode("utf-8"))
        except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
            raise WriteRefused("config-not-json", f"Secret {name}: data.config does not decode to JSON ({type(exc).__name__}); "
                                                  "fix the Secret where it is written, then rotate") from None
        if not isinstance(config, dict):
            raise WriteRefused("config-not-json", f"Secret {name}: data.config is not a JSON object; fix the Secret where it is written, then rotate")
        config.pop("oauth", None)
        config["bearerToken"] = token.strip()
        data["config"] = base64.b64encode(json.dumps(config).encode("utf-8")).decode("ascii")
        obj["data"] = data
        obj.pop("stringData", None)
        try:
            host_client._send(client, "PUT", _path(namespace, name), json=obj, secrets=(token, data["config"]))
        except ClusterError as exc:
            # The object carries the resourceVersion it was read with, so a Secret GitOps (or another
            # tab) rewrote between the read and this PUT is a 409 from the API server — a named conflict
            # the person can act on, not "unreachable" (round 2, Grok C16).
            if exc.message.startswith("HTTP 409"):
                raise WriteRefused("secret-changed", f"Secret {name} changed since it was read — GitOps or another "
                                                     "writer got there first; refresh and rotate again", conflict=True) from exc
            raise _failed(exc, token, data["config"]) from exc
    event(log, logging.INFO, "cluster-secret-rotated", secret=name, namespace=namespace, cluster=cluster,
          by=viewer, secrets=(token,))


def store_lookup(host_client: ClusterClient, namespace: str, name: str, *, token: str, cluster: str,
                 source_namespace: str, source_service_account: str, lookup_account: str) -> None:
    """SPEC_S4b: a Secret that DECLARED `saTokenLookup` becomes the credential it asked for, in place.

    Why in place and not a second Secret (SPEC_S4 §1): a Secret is named for its cluster and the
    reader fails closed on two Secrets for one cluster, so a `create` beside the declaring Secret is
    `secret-exists` and any other name is `duplicate-cluster-name` — neither loads. `config` becomes
    `{bearerToken, tlsClientConfig}`: the mode and bootstrap keys leave (the parser refuses them
    beside a credential) and the annotations keep the memory of the mode. `tlsClientConfig` is kept
    as declared — it is the trust that just verified both hosts. Labels and `managed-by` are kept:
    the lookup did not create this Secret. The decode refusal and the 409 are `rotate`'s, for the
    reasons stated there.
    """
    with host_client._client() as client:
        obj = _read_ours(host_client, client, namespace, name)
        data = obj.get("data") or {}
        try:
            config = json.loads(base64.b64decode(data.get("config") or "", validate=True).decode("utf-8"))
        except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
            raise WriteRefused("config-not-json", f"Secret {name}: data.config does not decode to JSON ({type(exc).__name__}); "
                                                  "fix the Secret where it is written") from None
        if not isinstance(config, dict):
            raise WriteRefused("config-not-json", f"Secret {name}: data.config is not a JSON object; fix the Secret where it is written")
        for key in (*CONNECTION_KEYS, "oauth"):
            config.pop(key, None)
        config["bearerToken"] = token.strip()
        data["config"] = base64.b64encode(json.dumps(config, separators=(",", ":")).encode("utf-8")).decode("ascii")
        obj["data"] = data
        obj.pop("stringData", None)
        meta = obj.setdefault("metadata", {})
        meta["annotations"] = {**(meta.get("annotations") or {}),
                               TOKEN_SOURCE_ANNOTATION: TOKEN_SOURCE_LOOKUP,
                               SOURCE_NAMESPACE_ANNOTATION: source_namespace,
                               SOURCE_SERVICE_ACCOUNT_ANNOTATION: source_service_account,
                               LOOKUP_ACCOUNT_ANNOTATION: lookup_account}
        try:
            host_client._send(client, "PUT", _path(namespace, name), json=obj, secrets=(token, data["config"]))
        except ClusterError as exc:
            if exc.message.startswith("HTTP 409"):
                raise WriteRefused("secret-changed", f"Secret {name} changed since it was read — GitOps or another "
                                                     "writer got there first; the next attempt reads it again", conflict=True) from exc
            raise _failed(exc, token, data["config"]) from exc
    event(log, logging.INFO, "cluster-secret-rotated", secret=name, namespace=namespace, cluster=cluster,
          by=MANAGED_BY_LOOKUP, secrets=(token,))


def delete(host_client: ClusterClient, namespace: str, name: str, *, viewer: str, cluster: str) -> None:
    """C4: DELETE the Secret; the next discovery retires the cluster, its rows kept."""
    with host_client._client() as client:
        _read_ours(host_client, client, namespace, name)
        try:
            host_client._send(client, "DELETE", _path(namespace, name))
        except ClusterError as exc:
            raise _failed(exc) from exc
    event(log, logging.INFO, "cluster-secret-deleted", secret=name, namespace=namespace, cluster=cluster, by=viewer)


def test_connection(req: CreateRequest, namespace: str, *, host_name: str | None, timeout: float, viewer: str) -> dict:
    """C5: the request through the parser, then `/version` and `users/~` with that client. Nothing is
    stored; the log line names the person and the server, never a field of the request."""
    parsed = validate(req, namespace, host_name=host_name, taken={})
    probe = ClusterClient(parsed, timeout=timeout)
    out: dict = {"reachable": False, "server_version": None, "identity": None, "error": None}
    try:
        with probe._client() as client:
            version = probe._get(client, "/version", {})
            out["server_version"] = version.get("gitVersion")
            try:
                me = probe._get(client, "/apis/user.openshift.io/v1/users/~", {})
                out["identity"] = (me.get("metadata") or {}).get("name")
            except ClusterError as exc:
                # A 404 is an ordinary Kubernetes without the OpenShift user API: the credential
                # still authenticated, so the test passed. Anything else did not.
                if not exc.message.startswith("HTTP 404"):
                    raise
            # REACHABLE IS SET LAST, after the credential has been used for something the API server
            # actually authorises. `/version` is open on OpenShift — it answers an anonymous request —
            # so setting it there reported a working connection for a token that was expired, revoked
            # or simply wrong, which is the one answer this control exists to give (review of #237,
            # Grok). The order is the assertion.
            out["reachable"] = True
    except ClusterError as exc:
        # The probe client redacts its own token from what the remote echoes; scrubbed again here so the
        # sentence that reaches the page never depends on which client raised it.
        out["error"] = _scrub(f"{exc.outcome}: {exc.message}", req.token)
    event(log, logging.INFO, "connection-tested", cluster=req.name, server=req.server, by=viewer,
          outcome="reachable" if out["reachable"] else "unreachable", secrets=(req.token,))
    return out


__all__ = ["CreateRequest", "WriteRefused", "WriteFailed", "SECRET_NAME_PREFIX", "MANAGED_BY_ANNOTATION",
           "MANAGED_BY_UI", "MANAGED_BY_LOOKUP",
           "TOKEN_SOURCE_ANNOTATION", "SOURCE_NAMESPACE_ANNOTATION", "SOURCE_SERVICE_ACCOUNT_ANNOTATION",
           "LOOKUP_ACCOUNT_ANNOTATION", "TOKEN_SOURCE_LOOKUP", "TOKEN_SOURCE_SELF_LOGIN",
           "TLS_MODES", "OAUTH_NOT_BUILT", "secret_object", "secret_name_for", "validate", "create", "rotate",
           "store_lookup", "delete", "test_connection", "AUTH_FAILED", "UNREACHABLE"]
