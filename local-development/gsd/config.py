"""Cluster configuration.

A cluster's bearer token is deliberately kept out of this module's data model. It is
resolved on demand from a file or environment variable (PLAN §5: "Tokens live in Secrets
mounted into the backend, never in the config object and never returned by the API"), so a
ClusterConfig can be serialised into an API response without leaking anything.

In-cluster the token arrives as a mounted Secret -> ``tokenFile``. For local development
against CRC it is easiest to pass ``oc whoami -t`` -> ``tokenEnv``. Both resolve to the
same thing; the plan's ``tokenSecretRef`` is the Kubernetes-side name of the file mount.
"""

from __future__ import annotations

import os
import ssl
from dataclasses import dataclass, field
from pathlib import Path

import yaml


class ConfigError(Exception):
    """Raised for a malformed or unusable cluster configuration."""


@dataclass(frozen=True)
class ClusterConfig:
    """One observed cluster.

    ``name`` doubles as the cluster id used in API paths (PLAN §11), so it must be URL-safe
    and stable — renaming a cluster orphans its stored observations.
    """

    name: str
    api_url: str
    token_env: str | None = None
    token_file: str | None = None
    ca_bundle_file: str | None = None
    insecure_skip_verify: bool = False
    enabled: bool = True

    def resolve_token(self) -> str:
        """Read the token at the moment it is needed.

        Deliberately re-read rather than cached: a mounted Secret is updated in place when
        the token is rotated, and a long-lived process that cached the value at startup
        would keep presenting the stale one until restarted (PLAN §13 Q1).
        """
        if self.token_file:
            try:
                token = Path(self.token_file).read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise ConfigError(
                    f"cluster {self.name!r}: cannot read tokenFile {self.token_file!r}: {exc}"
                ) from exc
            if not token:
                raise ConfigError(f"cluster {self.name!r}: tokenFile {self.token_file!r} is empty")
            return token

        if self.token_env:
            token = os.environ.get(self.token_env, "").strip()
            if not token:
                raise ConfigError(
                    f"cluster {self.name!r}: tokenEnv {self.token_env!r} is unset or empty"
                )
            return token

        raise ConfigError(f"cluster {self.name!r}: neither tokenFile nor tokenEnv configured")

    def verify(self) -> bool | ssl.SSLContext:
        """The value httpx expects for ``verify``.

        An SSLContext rather than a path: httpx deprecated the bare-string form, and
        building the context here fails loudly at configuration time if the CA bundle is
        missing or malformed, instead of at the first poll.
        """
        if self.insecure_skip_verify:
            return False

        # An explicit per-cluster bundle always wins.
        bundle = self.ca_bundle_file

        # Otherwise fall back to the cluster-wide trusted CA bundle, if one is mounted.
        #
        # This is what makes EXTERNAL clusters work without per-cluster configuration. Their
        # API servers are usually signed by a corporate CA, which is not in Python's default
        # trust store, so verification fails and the cluster shows as unreachable — a TLS
        # problem that presents as an outage. OpenShift will inject that CA for us: an empty
        # ConfigMap labelled `config.openshift.io/inject-trusted-cabundle: "true"` is filled
        # with the system bundle MERGED with proxy/cluster's trustedCA. Measured on a stock
        # cluster: 148 certificates.
        #
        # Deliberately a fallback rather than a merge: a cluster that names its own bundle is
        # making a specific statement about what it trusts, and silently widening that would
        # be the wrong kind of helpful.
        source = "caBundleFile"
        if not bundle:
            trusted = os.environ.get("GSD_TRUSTED_CA_FILE")
            if trusted and Path(trusted).is_file():
                bundle, source = trusted, "injected trusted CA bundle"

        if bundle:
            try:
                return ssl.create_default_context(cafile=bundle)
            except (OSError, ssl.SSLError) as exc:
                # Name the SOURCE, not just the path: "cannot load /etc/pki/..." sends
                # someone hunting a file, when the fix is in whichever of the two places
                # actually set it.
                raise ConfigError(
                    f"cluster {self.name!r}: cannot load {source} {bundle!r}: {exc}"
                ) from exc
        return True


@dataclass(frozen=True)
class Settings:
    """Process-wide settings."""

    clusters: list[ClusterConfig] = field(default_factory=list)
    poll_interval_seconds: int = 60
    """PLAN §6: 60s, far finer than the fastest schedule seen in practice."""

    schedule_grace_seconds: int = 120
    """Slack added before a CR is called late.

    A sync does not land exactly on its cron minute — 3-14s of scheduler latency was
    measured on CRC — and our own poll adds up to ``poll_interval_seconds`` on top. Without
    this grace, the age of a healthy CR briefly exceeds one interval near the end of every
    cycle and the state flaps to ``late`` on each pass. See state.py.
    """

    binding_interval_seconds: int = 300
    """How often to re-read RoleBindings/ClusterRoleBindings — deliberately slower than
    the group poll.

    Bindings change on administrative action, not on a sync schedule, so minute-level
    freshness buys nothing. The cost is not hypothetical: this resource is listed across
    every namespace, and at 100x the measured CRC scale (530 RoleBindings, 236
    ClusterRoleBindings) a refresh is roughly 154 paged API requests. Five minutes cuts
    that by 80% against a 60s poll while staying operationally current.
    """

    request_timeout_seconds: float = 15.0
    """Per-request timeout against a cluster's API server.

    Configurable rather than hardcoded because it is the main lever for not overwhelming
    a busy API server: a slow cluster should time out and degrade to a card, not stall its
    poll thread indefinitely.
    """

    db_path: str = "gsd.db"

    def cluster(self, name: str) -> ClusterConfig | None:
        for c in self.clusters:
            if c.name == name:
                return c
        return None


def _require(raw: dict, key: str, where: str) -> object:
    if key not in raw:
        raise ConfigError(f"{where}: missing required key {key!r}")
    return raw[key]


def load_settings(path: str | Path) -> Settings:
    """Load and validate settings from a YAML file.

    Validation is strict and up-front: a typo in a cluster entry should fail at startup
    with the offending key named, not surface later as a cluster that silently never polls.
    """
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise ConfigError(f"cannot read config {str(path)!r}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {str(path)!r}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: top level must be a mapping")

    entries = raw.get("clusters") or []
    if not isinstance(entries, list) or not entries:
        raise ConfigError(f"{path}: 'clusters' must be a non-empty list")

    known = {
        "name",
        "apiUrl",
        "tokenEnv",
        "tokenFile",
        "caBundleFile",
        "insecureSkipVerify",
        "enabled",
    }

    clusters: list[ClusterConfig] = []
    seen: set[str] = set()
    for i, entry in enumerate(entries):
        where = f"{path}: clusters[{i}]"
        if not isinstance(entry, dict):
            raise ConfigError(f"{where}: must be a mapping")

        unknown = set(entry) - known
        if unknown:
            raise ConfigError(f"{where}: unknown key(s) {sorted(unknown)}")

        name = str(_require(entry, "name", where))
        if name in seen:
            raise ConfigError(f"{where}: duplicate cluster name {name!r}")
        seen.add(name)

        if "/" in name:
            raise ConfigError(f"{where}: name {name!r} must not contain '/' — it is used in API paths")

        api_url = str(_require(entry, "apiUrl", where)).rstrip("/")
        if not api_url.startswith(("http://", "https://")):
            raise ConfigError(f"{where}: apiUrl must start with http:// or https://")

        if not entry.get("tokenEnv") and not entry.get("tokenFile"):
            raise ConfigError(f"{where}: one of tokenEnv or tokenFile is required")

        insecure = bool(entry.get("insecureSkipVerify", False))
        if insecure and entry.get("caBundleFile"):
            raise ConfigError(
                f"{where}: insecureSkipVerify and caBundleFile are mutually exclusive"
            )

        clusters.append(
            ClusterConfig(
                name=name,
                api_url=api_url,
                token_env=entry.get("tokenEnv"),
                token_file=entry.get("tokenFile"),
                ca_bundle_file=entry.get("caBundleFile"),
                insecure_skip_verify=insecure,
                enabled=bool(entry.get("enabled", True)),
            )
        )

    return Settings(
        clusters=clusters,
        poll_interval_seconds=int(raw.get("pollIntervalSeconds", 60)),
        schedule_grace_seconds=int(raw.get("scheduleGraceSeconds", 120)),
        binding_interval_seconds=int(raw.get("bindingIntervalSeconds", 300)),
        request_timeout_seconds=float(raw.get("requestTimeoutSeconds", 15.0)),
        # GSD_DB_PATH wins over the file so the config can ship as a ConfigMap that does
        # not need to know where the writable volume is mounted.
        db_path=os.environ.get("GSD_DB_PATH") or str(raw.get("dbPath", "gsd.db")),
    )
