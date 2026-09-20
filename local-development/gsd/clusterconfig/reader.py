"""One discovery: LIST the labelled Secrets in the pod's namespace, parse each, apply the duplicate and
shadow rules (SPEC_S1 C2/C3). Raises ClusterError when the LIST itself fails — the caller records it as
the cycle's finding and keeps the previous set."""

from __future__ import annotations

import logging

from ..config import ClusterConfig
from . import LABEL_SELECTOR
from .parser import Finding, parse_secret

log = logging.getLogger(__name__)


def discover(cluster_client, namespace: str, *, host_name: str | None,
             values_names: tuple[str, ...] = ()) -> tuple[list[ClusterConfig], list[Finding]]:
    path = f"/api/v1/namespaces/{namespace}/secrets"
    with cluster_client._client() as client:
        items = cluster_client._list_all_with(client, path, {"labelSelector": LABEL_SELECTOR})
    # Deterministic: two Secrets naming one cluster resolve the same way every cycle.
    items.sort(key=lambda o: str((o.get("metadata") or {}).get("name") or ""))
    clusters: list[ClusterConfig] = []
    findings: list[Finding] = []
    seen: dict[str, str] = {}
    for obj in items:
        parsed = parse_secret(obj, host_name=host_name)
        if isinstance(parsed, Finding):
            findings.append(parsed)
            log.warning("cluster Secret %s refused: %s (%s)", parsed.secret, parsed.code, parsed.detail)
            continue
        secret_name = parsed.source.split(":", 1)[1]
        if parsed.name in seen:
            findings.append(Finding(secret_name, "duplicate-cluster-name",
                                    f"{parsed.name} is already declared by Secret {seen[parsed.name]}; this one is ignored"))
            continue
        seen[parsed.name] = secret_name
        if parsed.name in values_names:
            findings.append(Finding(secret_name, "shadows-values-entry",
                                    f"{parsed.name} is also a values entry; the Secret wins"))
        if parsed.credential_kind == "oauth":
            findings.append(Finding(secret_name, "oauth-exchange-not-built",
                                    f"{parsed.name} declares oauth; the exchange is #119 P2 and the cluster is not polled"))
        clusters.append(parsed)
    return clusters, findings
