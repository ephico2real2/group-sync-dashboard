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
    # Deterministic: the findings list the same way every cycle.
    items.sort(key=lambda o: str((o.get("metadata") or {}).get("name") or ""))
    parsed_ok: list[ClusterConfig] = []
    findings: list[Finding] = []
    for obj in items:
        parsed = parse_secret(obj, host_name=host_name)
        if isinstance(parsed, Finding):
            findings.append(parsed)
            log.warning("cluster Secret %s refused: %s (%s)", parsed.secret, parsed.code, parsed.detail)
            continue
        parsed_ok.append(parsed)
    # FAIL CLOSED ON A DUPLICATE NAME (design review of #230, OB2). "The first by metadata.name wins"
    # let a Secret named to sort first — `aaa-anything` — replace the server and the token of a
    # cluster a later-sorting Secret declares: a hijack by naming, open to anyone who may create a
    # Secret in this namespace, and invisible because the winner looked like an ordinary cluster.
    # Two Secrets naming one cluster now load NEITHER; each is a finding naming the other, so the
    # cluster is retired for the cycle (its rows kept, #96) and the tab says why.
    by_name: dict[str, list[ClusterConfig]] = {}
    for c in parsed_ok:
        by_name.setdefault(c.name, []).append(c)
    clusters: list[ClusterConfig] = []
    for name, group in by_name.items():
        if len(group) > 1:
            names = sorted(c.source.split(":", 1)[1] for c in group)
            for c in group:
                mine = c.source.split(":", 1)[1]
                others = ", ".join(n for n in names if n != mine)
                findings.append(Finding(mine, "duplicate-cluster-name",
                                        f"{name} is also declared by Secret {others}; neither is loaded until one is removed"))
                log.warning("cluster Secret %s refused: duplicate-cluster-name (%s also in %s)", mine, name, others)
            continue
        parsed = group[0]
        secret_name = parsed.source.split(":", 1)[1]
        if parsed.name in values_names:
            findings.append(Finding(secret_name, "shadows-values-entry",
                                    f"{parsed.name} is also a values entry; the Secret wins"))
        if parsed.credential_kind == "oauth":
            findings.append(Finding(secret_name, "oauth-exchange-not-built",
                                    f"{parsed.name} declares oauth; the exchange is #119 P2 and the cluster is not polled"))
        clusters.append(parsed)
    return clusters, findings
