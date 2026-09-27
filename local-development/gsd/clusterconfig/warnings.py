"""Advisories about effective entries; these never refuse a configuration."""
from __future__ import annotations

from ..config import ClusterConfig
from ..fleetlookup import CredentialGate


def shared_api_urls(clusters: list[ClusterConfig]) -> dict[str, tuple[str, ...]]:
    groups: dict[str, list[str]] = {}
    for cluster in clusters:
        if not cluster.enabled:
            continue    # not polled, so it doubles nothing — the reason refused Secrets are left out (#314)
        url = CredentialGate._target(cluster.api_url)
        groups.setdefault(url, []).append(cluster.name)
    return {url: tuple(sorted(names)) for url, names in sorted(groups.items()) if len(names) > 1}


def shared_api_warnings(clusters: list[ClusterConfig]) -> list[dict]:
    return [{"code": "shared-api-url", "clusters": list(names),
             "detail": f"{', '.join(names)} declare the same API URL: {url}. "
                       "Each entry is still polled and counted on its own."}
            for url, names in shared_api_urls(clusters).items()]
