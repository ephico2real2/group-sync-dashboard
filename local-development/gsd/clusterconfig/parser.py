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
    BOOTSTRAP_KEY, CLUSTER_IDENTITIES, CLUSTER_VISIBILITIES, CONNECTION_KEYS, CONNECTION_MODE_KEYS,
    VISIBILITY_REMOTE_SAR, ClusterConfig, valid_bootstrap_username,
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
#: The `config` keys this contract accepts. The three connection-mode keys are the values loader's
#: (SPEC_S3 §2: one declaration, two readers); the guard in tests/test_connection_modes.py holds the
#: two sets together.
ACCEPTED_CONFIG_KEYS = ("bearerToken", "oauth", "tlsClientConfig", *CONNECTION_KEYS)

#: Every key name a finding will repeat back. A finding's detail is LOGGED (the poller's
#: `secret-refused` line) and SERVED (`/api/clusterconfigs`), and the parse-phase announcement is
#: the only one of the eight log sites that passes no `secrets=` — it cannot, because a refused
#: Secret never became a ClusterConfig and the poller holds none of its values to strip. Measured
#: (second pass, OB3 C2): a `config` of `{"<a 43-character secret>": 1}` put that string verbatim
#: into `secret-refused … detail=` and into the tab. A key position is a place a credential can
#: land, so the text is repeated only when it is a name this contract already knows — a case typo
#: of one of ours, or one of Argo's we refuse by name — and anything else is described by its
#: length: the same no-echo contract `_apply_per_logger_levels` applies to a miswired variable.
_ECHOABLE_KEYS = {k.lower() for k in (
    *_REFUSED_CONFIG_KEYS, *_REFUSED_TLS_KEYS,
    "bearerToken", "oauth", "tlsClientConfig", "caData", "insecure", "username", "password",
    "name", "server", "config", "visibility", "identity", "enabled",
    "namespaces", "clusterResources", "project", "shard", "dashboardController",
    *CONNECTION_KEYS,   # SPEC_S3 §4: a new key joins here too, or a typo is reported by its length
)}


def _unknown_key(key: str, *, prefix: str, where: str) -> str:
    """The detail for a key this contract does not define, echoing it only when it is safe to."""
    if key.lower() in _ECHOABLE_KEYS:
        return f"{prefix}{key}: not a key this contract defines"
    return (f"{where} has a {len(key)}-character key this contract does not define. It is not "
            f"repeated here, in case something other than a key name was written into it")


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

    # The controller flag is a VALUES concept (#249): it names this pod's own cluster, and a
    # Secret-sourced cluster is by definition remote — the chart writes the stanza for the cluster
    # the pod runs on. Accepting it here would let a Secret claim to be the host, which decides the
    # oauth-proxy's target and what `same-as-host` resolves against. Refused by name, not ignored.
    if "dashboardController" in data:
        return finding("unsupported-config-key",
                       "data.dashboardController: the controller is declared in the chart's values, "
                       "not by a Secret — a Secret-sourced cluster is remote by definition")

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
        if key not in ACCEPTED_CONFIG_KEYS:
            return finding("unsupported-config-key", _unknown_key(key, prefix="", where="config"))

    token = config.get("bearerToken")
    oauth = config.get("oauth")
    # SPEC_S3 §4 (S3a): a connection mode in `config` — the same three keys the values loader knows —
    # with the Secret's own rule: two sources of truth is a FINDING on the tab, never a crash.
    modes: list[str] = []
    for key in CONNECTION_MODE_KEYS:
        if key in config:
            if not isinstance(config[key], bool):
                return finding("unsupported-config-key", f"config.{key}: must be a boolean")
            if config[key]:
                modes.append(key)
    if len(modes) > 1:
        return finding("credential-ambiguous", "config declares both saTokenLookup and userSelfLogin; declare one")
    mode = modes[0] if modes else None
    if mode is not None and (token is not None or oauth is not None):
        return finding("credential-ambiguous",
                       f"config carries a credential and {mode}: two sources of truth for one credential; declare one")
    bootstrap = config.get(BOOTSTRAP_KEY)
    if bootstrap is not None:
        if not valid_bootstrap_username(bootstrap):
            return finding("unsupported-config-key",
                           f"config.{BOOTSTRAP_KEY}: must be a username (letters, digits, '.', '_', '@', '-')")
        if mode is None:
            return finding("unsupported-config-key",
                           f"config.{BOOTSTRAP_KEY} without saTokenLookup or userSelfLogin configures a login that would never happen")
    if token is not None and oauth is not None:
        return finding("credential-ambiguous", "config carries both bearerToken and oauth; declare one")
    if token is None and oauth is None and mode is None:
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
            return finding("unsupported-config-key",
                           _unknown_key(key, prefix="tlsClientConfig.", where="tlsClientConfig"))
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
        sa_token_lookup=mode == "saTokenLookup", user_self_login=mode == "userSelfLogin",
        ldap_connection_bootstrap=str(bootstrap) if bootstrap is not None else None,
    )
