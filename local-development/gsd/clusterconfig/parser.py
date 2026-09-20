"""One Secret → one ClusterConfig, or one Finding (SPEC_S1 contract C1/C2). Pure: no I/O, no logging of
values — a finding names the Secret and the offending KEY, never what was in it."""

from __future__ import annotations

import base64
import binascii
import json
import re
import ssl
from dataclasses import dataclass

from ..config import (
    CLUSTER_IDENTITIES, CLUSTER_VISIBILITIES, VISIBILITY_REMOTE_SAR, ClusterConfig,
)

from . import FINDING_CODES

IN_CLUSTER_SERVER = "https://kubernetes.default.svc"

# The cluster id is used in API paths (PLAN §11): a DNS-label shape keeps it URL-safe and stable.
_NAME = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
_SERVER = re.compile(r"^https://[^/\s]+$")

# Argo's `config` keys, each with the reason it is refused, so the finding can say why and not only
# that (SPEC_S1 C1). `bearerToken`, `oauth` and `tlsClientConfig` are the accepted ones.
_REFUSED_CONFIG_KEYS = {
    "username": "the API server takes no HTTP basic auth; use oauth {username, password}",
    "password": "the API server takes no HTTP basic auth; use oauth {username, password}",
    "execProviderConfig": "the pod runs no exec plugins",
    "awsAuthConfig": "the pod runs no exec plugins",
    "proxyUrl": "not supported",
    "disableCompression": "not supported",
}
_REFUSED_TLS_KEYS = {"certData": "the pod holds no client certificate", "keyData": "the pod holds no client certificate",
                     "serverName": "not supported"}


@dataclass(frozen=True)
class Finding:
    secret: str      # metadata.name
    code: str        # one of FINDING_CODES
    detail: str      # the key or the reason; never a credential

    def __post_init__(self) -> None:
        if self.code not in FINDING_CODES:
            raise ValueError(f"unknown finding code {self.code!r}")

    def public(self) -> dict:
        return {"secret": self.secret, "code": self.code, "detail": self.detail}


def _data(obj: dict) -> dict[str, str]:
    """The Secret's data decoded (the API serves `data` base64; a test fixture may hand `stringData`)."""
    out: dict[str, str] = {}
    for key, value in (obj.get("stringData") or {}).items():
        out[key] = str(value)
    for key, value in (obj.get("data") or {}).items():
        if key in out:
            continue
        try:
            out[key] = base64.b64decode(value, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, TypeError, ValueError):
            out[key] = ""
    return out


def parse_secret(obj: dict, *, host_name: str | None) -> ClusterConfig | Finding:
    meta = obj.get("metadata") or {}
    secret_name = str(meta.get("name") or "?")
    data = _data(obj)

    def finding(code: str, detail: str) -> Finding:
        return Finding(secret_name, code, detail)

    name = (data.get("name") or "").strip()
    if not name:
        return finding("name-missing", "data.name is required: the cluster id the dashboard shows")
    if not _NAME.match(name):
        return finding("name-invalid", "data.name must be a DNS label (lowercase letters, digits, hyphens; ≤ 63)")
    server = (data.get("server") or "").strip()
    if not server:
        return finding("server-missing", "data.server is required: the API URL")
    if not _SERVER.match(server):
        return finding("server-invalid", "data.server must be https://host[:port] with no path")
    if host_name is not None and (name == host_name or server == IN_CLUSTER_SERVER):
        # The departure from Argo (spec notes): the host authenticates the reader; a Secret must not
        # be able to replace it.
        return finding("host-cluster-not-from-secret",
                       "the host cluster is values.yaml clusters[0] and is never sourced from a Secret")

    raw_config = data.get("config")
    if raw_config is None or not raw_config.strip():
        return finding("config-missing", "data.config is required: a JSON object")
    try:
        config = json.loads(raw_config)
    except json.JSONDecodeError as exc:
        return finding("config-not-json", f"{exc.msg}: line {exc.lineno} column {exc.colno}")
    if not isinstance(config, dict):
        return finding("config-not-json", "data.config must be a JSON object")
    for key in config:
        if key in _REFUSED_CONFIG_KEYS:
            return finding("unsupported-config-key", f"{key}: {_REFUSED_CONFIG_KEYS[key]}")
        if key not in ("bearerToken", "oauth", "tlsClientConfig"):
            return finding("unsupported-config-key", f"{key}: not a key this contract defines")

    token = config.get("bearerToken")
    oauth = config.get("oauth")
    if token is not None and oauth is not None:
        return finding("credential-ambiguous", "config carries both bearerToken and oauth; declare one")
    if token is None and oauth is None:
        return finding("credential-missing", "config needs bearerToken or oauth {username, password}")
    if token is not None and (not isinstance(token, str) or not token.strip()):
        return finding("credential-missing", "config.bearerToken is empty")
    oauth_user = oauth_pass = None
    if oauth is not None:
        if not isinstance(oauth, dict) or not str(oauth.get("username") or "").strip() \
                or not str(oauth.get("password") or "").strip():
            return finding("credential-missing", "config.oauth needs both username and password")
        oauth_user, oauth_pass = str(oauth["username"]), str(oauth["password"])

    tls = config.get("tlsClientConfig") or {}
    if not isinstance(tls, dict):
        return finding("unsupported-config-key", "tlsClientConfig: must be an object")
    for key in tls:
        if key in _REFUSED_TLS_KEYS:
            return finding("unsupported-config-key", f"tlsClientConfig.{key}: {_REFUSED_TLS_KEYS[key]}")
        if key not in ("caData", "insecure"):
            return finding("unsupported-config-key", f"tlsClientConfig.{key}: not a key this contract defines")
    insecure = tls.get("insecure", False)
    if not isinstance(insecure, bool):
        return finding("unsupported-config-key", "tlsClientConfig.insecure: must be a boolean")
    ca_data = None
    if tls.get("caData"):
        if insecure:
            return finding("insecure-with-ca", "tlsClientConfig.insecure=true beside caData: choose one")
        try:
            ca_data = base64.b64decode(str(tls["caData"]), validate=True).decode("utf-8")
            ssl.create_default_context(cadata=ca_data)    # load it now: a bundle that does not load is a finding here
        except (binascii.Error, UnicodeDecodeError, ValueError, ssl.SSLError) as exc:
            return finding("ca-data-invalid", f"tlsClientConfig.caData does not decode to a PEM bundle that loads: {type(exc).__name__}")

    visibility = (data.get("visibility") or "").strip() or None
    allowed = tuple(v for v in CLUSTER_VISIBILITIES if v != VISIBILITY_REMOTE_SAR)
    if visibility is not None and visibility not in allowed:
        # remote-sar needs a TierResolver built at app start for that cluster (api.py's remote
        # resolvers); a cluster that appears at runtime has none, so it would fail open. S2 builds
        # them at discovery; until then the Secret says inherit, self-only or hidden.
        return finding("visibility-invalid", f"data.visibility must be one of {', '.join(allowed)}"
                       + (" (remote-sar for a Secret-sourced cluster is S2)" if visibility == VISIBILITY_REMOTE_SAR else ""))
    identity = (data.get("identity") or "").strip() or None
    if identity is not None and identity not in CLUSTER_IDENTITIES:
        return finding("identity-invalid", f"data.identity must be one of {', '.join(CLUSTER_IDENTITIES)}")
    enabled_raw = (data.get("enabled") or "true").strip().lower()
    if enabled_raw not in ("true", "false"):
        return finding("enabled-invalid", 'data.enabled must be "true" or "false"')

    from . import SECRET_TYPE_LABEL   # local: the package imports this module
    labels = tuple(sorted((str(k), str(v)) for k, v in (meta.get("labels") or {}).items() if k != SECRET_TYPE_LABEL))
    return ClusterConfig(
        name=name, api_url=server, enabled=enabled_raw == "true",
        insecure_skip_verify=insecure, visibility=visibility, identity=identity,
        token_value=token.strip() if isinstance(token, str) else None, ca_data=ca_data,
        oauth_username=oauth_user, oauth_password=oauth_pass,
        source=f"secret:{secret_name}", labels=labels,
    )
