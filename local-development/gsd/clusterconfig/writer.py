"""The Cluster Configurations tab's writes (docs/specs/SPEC_S2_cluster_configurations_tab.md, C2–C5):
create a labelled Secret, rotate its bearer token in place, delete it, and test a connection before
writing anything.

Every write goes through the HOST cluster's client into the pod's own namespace and touches only a
Secret carrying our label — the app checks the label itself before an update or a delete, because
RBAC cannot scope a verb by label. The request is validated by the SAME parser discovery runs
(`parse_secret` on the object about to be written), so a request this module accepts is a Secret the
next discovery accepts, byte for byte. The credential is never logged here: a finding names the key,
the audit line names the person, the verb and the Secret.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
from dataclasses import dataclass, field

from ..config import ClusterConfig
from ..kube import AUTH_FAILED, FORBIDDEN, UNREACHABLE, ClusterClient, ClusterError
from . import SECRET_TYPE_CLUSTER, SECRET_TYPE_LABEL
from .parser import Finding, parse_secret

log = logging.getLogger(__name__)

SECRET_NAME_PREFIX = "gsd-cluster-"
MANAGED_BY_ANNOTATION = "groupsync-dashboard.io/managed-by"
MANAGED_BY_UI = "ui"
LABEL_DOMAIN = "groupsync-dashboard.io/"
TLS_MODES = ("caData", "trustedBundle", "insecure")
OAUTH_NOT_BUILT = "the password-for-token exchange is #119 P2, not built yet"


class WriteRefused(Exception):
    """A request the contract refuses before any write: `code` is a finding code (or `duplicate-cluster-name`,
    `not-a-secret-cluster`, `not-our-secret`, `secret-exists`, `writes-disabled`), `detail` the sentence."""

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
        config["bearerToken"] = "<redacted>" if redact else (req.token or "")
    labels = {SECRET_TYPE_LABEL: SECRET_TYPE_CLUSTER, **{str(k): str(v) for k, v in (req.labels or {}).items()}}
    return {
        "apiVersion": "v1", "kind": "Secret",
        "metadata": {"name": secret_name_for(req.name), "namespace": namespace, "labels": labels,
                     "annotations": {MANAGED_BY_ANNOTATION: MANAGED_BY_UI}},
        "type": "Opaque",
        # Compact separators: the page's twin is JSON.stringify under a `|-` block, and the promise is that
        # the two Secrets are equal BYTE FOR BYTE, `config` included — not merely equal once parsed.
        "stringData": {"name": req.name, "server": req.server, "config": json.dumps(config, separators=(",", ":")),
                       "visibility": req.visibility, "identity": req.identity, "enabled": "true"},
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
    if req.tls_mode not in TLS_MODES:
        raise WriteRefused("unsupported-config-key", f"tls.mode must be one of {', '.join(TLS_MODES)}")
    if req.tls_mode == "caData":
        if not req.ca_data:
            raise WriteRefused("ca-data-invalid", "tls.mode caData needs tls.caData (a base64 PEM bundle)")
        try:
            base64.b64decode(req.ca_data, validate=True)
        except (binascii.Error, ValueError):
            raise WriteRefused("ca-data-invalid", "tls.caData must be a base64 PEM bundle") from None
    for key in req.labels or {}:
        if str(key).startswith(LABEL_DOMAIN):
            raise WriteRefused("unsupported-config-key", f"label {key}: the {LABEL_DOMAIN} prefix is the app's")
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
    """Remove the request's own credential from a sentence about to leave this module. The host
    client redacts ITS token from what the API server echoes; the token a caller asked us to write is
    in the request body, which a 4xx from the API server (or a proxy's error page) can quote back —
    and that sentence becomes a 502 detail, a connection-test `error` and a log line. So every
    failure message passes through here before it is raised (review of #237, Codex C2: an echoing
    API server put the sentinel into the 502 body). Each caller names EVERY form it put on the wire:
    the plain token, and — for a rotate, whose body is `data` — the base64 blob that encodes it, which
    a plain-text search cannot see through (measured: the first test of this scrub failed on it)."""
    for secret in secrets:
        if secret and len(secret.strip()) >= 8 and secret.strip() in text:
            text = text.replace(secret.strip(), "<redacted>")
    return text


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
            host_client._send(client, "POST", _path(namespace), json=obj)
        except ClusterError as exc:
            raise _failed(exc, req.token) from exc
    log.info("cluster Secret %s created by %s for cluster %s", name, viewer, req.name)
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
            host_client._send(client, "PUT", _path(namespace, name), json=obj)
        except ClusterError as exc:
            raise _failed(exc, token, data["config"]) from exc
    log.info("cluster Secret %s credential rotated by %s for cluster %s", name, viewer, cluster)


def delete(host_client: ClusterClient, namespace: str, name: str, *, viewer: str, cluster: str) -> None:
    """C4: DELETE the Secret; the next discovery retires the cluster, its rows kept."""
    with host_client._client() as client:
        _read_ours(host_client, client, namespace, name)
        try:
            host_client._send(client, "DELETE", _path(namespace, name))
        except ClusterError as exc:
            raise _failed(exc) from exc
    log.info("cluster Secret %s deleted by %s for cluster %s", name, viewer, cluster)


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
    log.info("connection test by %s against %s: %s", viewer, req.server,
             "reachable" if out["reachable"] else "unreachable")
    return out


__all__ = ["CreateRequest", "WriteRefused", "WriteFailed", "SECRET_NAME_PREFIX", "MANAGED_BY_ANNOTATION",
           "TLS_MODES", "OAUTH_NOT_BUILT", "secret_object", "secret_name_for", "validate", "create", "rotate",
           "delete", "test_connection", "AUTH_FAILED", "UNREACHABLE"]
