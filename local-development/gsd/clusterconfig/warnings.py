"""Advisories about effective entries; these never refuse a configuration."""
from __future__ import annotations

from datetime import datetime, timezone

from ..config import ClusterConfig, Settings
from ..fleetlookup import CredentialGate
from .ca import EXPIRED, EXPIRING, NOT_YET, summarise_cluster


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


def ca_warnings(clusters: list[ClusterConfig], settings: Settings,
                now: datetime | None = None) -> list[dict]:
    """Expiry and enterprise-root advisories; these never refuse a configuration."""
    now = now or datetime.now(timezone.utc)
    words = {EXPIRING: "ca-expiring", EXPIRED: "ca-expired", NOT_YET: "ca-not-yet-valid"}
    out: list[dict] = []
    for cluster in clusters:
        if not cluster.enabled:
            continue
        trust = summarise_cluster(cluster, settings, now)
        if trust["enterpriseRoot"] is False:
            pin = settings.enterprise_ca_sha256 or settings.enterprise_ca_subject
            out.append({"code": "ca-not-enterprise", "clusters": [cluster.name],
                        "detail": f"{cluster.name} does not trust the configured enterprise root "
                                  f"({pin}). The cluster is still polled."})
        for cert in trust["certificates"]:
            code = words.get(cert["validity"])
            if not code:
                continue
            when = cert["notBefore"] if cert["validity"] == NOT_YET else cert["notAfter"]
            out.append({"code": code, "clusters": [cluster.name],
                        "detail": f"{cluster.name}'s CA {cert['subject']} is "
                                  f"{cert['validity'].replace('-', ' ')} ({when}). "
                                  f"The cluster is still polled."})
    return out
