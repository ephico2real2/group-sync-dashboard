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
# host[:port] and nothing else. `@`, `?` and `#` are refused by name because `api_url` is served at
# EVERY tier: a `server` of https://user:token@host would publish a credential to a self reader —
# and the whole point of this contract is that the credential lives in the Secret (review of #235,
# the Fable seat). A path is refused too, as it always was.
_SERVER = re.compile(r"^https://[^/\s@?#]+$")

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


def _data(obj: dict) -> tuple[dict[str, str], set[str]]:
    """The Secret's data decoded, and the keys whose value did not decode.

    The API serves `data` base64; a test fixture may hand `stringData`. A value that is not base64 or
    not UTF-8 used to become `""`, which the caller then reported as "data.config is required" — false,
    and it sends the operator to the wrong line of the manifest (review of #235, OB3 F5). The key is
    returned as undecodable instead, so the finding says what is actually wrong. No new finding code:
    each key keeps the one it already owns, because that set is a page contract (SPEC_S1 §S1.2).
    """
    out: dict[str, str] = {}
    undecodable: set[str] = set()
    for key, value in (obj.get("stringData") or {}).items():
        out[key] = str(value)
    for key, value in (obj.get("data") or {}).items():
        if key in out:
            continue
        try:
            out[key] = base64.b64decode(value, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, TypeError, ValueError):
            out[key] = ""
            undecodable.add(key)
    return out, undecodable


def parse_secret(obj: dict, *, host_name: str | None) -> ClusterConfig | Finding:
    meta = obj.get("metadata") or {}
    secret_name = str(meta.get("name") or "?")
    data, undecodable = _data(obj)

    def finding(code: str, detail: str) -> Finding:
        return Finding(secret_name, code, detail)

    # A value that is present but did not decode is reported against the key's OWN code, before the
    # key is read as absent — "data.config is required" for a config that IS there, only malformed,
    # is a wrong diagnosis and costs the operator the search (review of #235, OB3 F5).
    for key, code in (("name", "name-missing"), ("server", "server-missing"), ("config", "config-missing")):
        if key in undecodable:
            return finding(code, f"data.{key} is present but is not base64-encoded UTF-8 text; write it "
                                 "under stringData, or base64 it with no line breaks")

    name = (data.get("name") or "").strip()
    if not name:
        return finding("name-missing", "data.name is required: the cluster id the dashboard shows")
    if not _NAME.match(name):
        return finding("name-invalid", "data.name must be a DNS label (lowercase letters, digits, hyphens; ≤ 63)")
    server = (data.get("server") or "").strip()
    if not server:
        return finding("server-missing", "data.server is required: the API URL")
    if not _SERVER.match(server):
        return finding("server-invalid", "data.server must be https://host[:port] — no path, and no credentials, query or fragment: this value is shown to every reader")
    if host_name is not None and (name == host_name or server == IN_CLUSTER_SERVER):
        # The departure from Argo (spec notes): the host authenticates the reader; a Secret must not
        # be able to replace it.
        return finding("host-cluster-not-from-secret",
                       "the host cluster is values.yaml clusters[0] and is never sourced from a Secret")

    # Argo's scoping and routing keys (`namespaces`, `clusterResources`, `project`, `shard` —
    # util/db/cluster.go SecretToCluster) narrow what Argo reads on that cluster or route it to a
    # shard. This contract has no equivalent: a Secret copied from Argo with `namespaces: team-a`
    # would be read as a FULL cluster — the opposite of what its author declared — so it is refused
    # with the key named rather than silently over-read (design review of #230, OB2).
    for key in ("namespaces", "clusterResources", "project", "shard"):
        if key in data:
            return finding("unsupported-config-key",
                           f"data.{key}: Argo CD's scope/routing key; this contract reads the whole "
                           "cluster and cannot honour it")

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
    # Trust is one of three (the operator's ruling, 2026-09-20 — SPEC_S1 notes): no caData → the
    # dashboard's own trust store (GSD_TRUSTED_CA_FILE + the system store, ClusterConfig.verify's default);
    # caData → that bundle for this cluster alone; insecure: true → verification off. Both named at once
    # is refused, the same rule load_settings applies to insecureSkipVerify beside caBundleFile.
    ca_data = None
    # PRESENCE, not truthiness (review of #235, Codex C7): `caData: ""` beside `insecure: true` used to
    # slip past this refusal and poll insecurely, and an empty caData alone silently became the
    # trusted-bundle mode — in both cases the operator declared one thing and got another. An empty
    # value is a malformed declaration, not an absent key.
    if "caData" in tls:
        if not str(tls.get("caData") or "").strip():
            return finding("unsupported-config-key",
                           "tlsClientConfig.caData is empty: omit the key for the dashboard's trust "
                           "store, or give a base64 PEM bundle")
        if insecure:
            return finding("insecure-with-ca", "tlsClientConfig.caData and tlsClientConfig.insecure=true are both set: choose one")
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
