"""One discovery: LIST the labelled Secrets in the pod's namespace, parse each, apply the duplicate and
shadow rules (SPEC_S1 C2/C3). Raises ClusterError when the LIST itself fails — the caller records it as
the cycle's finding and keeps the previous set."""

from __future__ import annotations

import logging

from ..config import ClusterConfig
from . import LABEL_SELECTOR
from .events import failure
from .parser import Finding, parse_secret

log = logging.getLogger(__name__)

#: What to do about each refusal, in the operator's terms rather than the parser's. `action=` is the
#: fix, not the diagnosis (#245): a line that says only what broke leaves the reader to translate,
#: and this module is the one that knows the translation. A code with no entry falls back to the
#: tab, which always has the long form.
_ACTIONS = {
    "name-missing": "set stringData.name to the cluster id the dashboard should show",
    "name-invalid": "stringData.name must be a DNS-1123 name: lowercase letters, digits and -",
    "server-missing": "set stringData.server to the cluster's API URL",
    "server-invalid": "stringData.server must be an https:// URL with no userinfo, query or fragment",
    "config-missing": "add a config key holding the credential as JSON",
    "config-not-json": "config must be a JSON object",
    "unsupported-config-key": "remove the key, or use one this dashboard reads",
    "credential-missing": "give config a bearerToken, or username and password (#119 P2)",
    "credential-ambiguous": "give config one credential, not two",
    "ca-data-invalid": "tlsClientConfig.caData must be base64 of a PEM bundle that loads",
    "insecure-with-ca": "choose one: caData to trust a bundle, or insecure to verify nothing",
    "visibility-invalid": "visibility must be inherit, self-only or hidden",
    "identity-invalid": "identity must be none or same-as-host",
    "enabled-invalid": 'enabled must be "true" or "false"',
    "host-cluster-not-from-secret": "the host cluster comes from the chart's values, not a Secret",
    "duplicate-cluster-name": "remove one of the two Secrets, or rename the cluster in one",
    "oauth-exchange-not-built": "use a bearerToken until the password exchange lands (#119 P2)",
}


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
            failure(log, "secret-refused", phase="parse", outcome=parsed.code,
                    action=_ACTIONS.get(parsed.code, "see the Cluster Configurations tab"),
                    secret=parsed.secret, detail=parsed.detail)
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
                failure(log, "secret-refused", phase="parse", outcome="duplicate-cluster-name",
                        action=_ACTIONS["duplicate-cluster-name"], secret=mine, cluster=name,
                        detail=f"also declared by {others}; neither is loaded")
            continue
        parsed = group[0]
        secret_name = parsed.source.split(":", 1)[1]
        if parsed.name in values_names:
            findings.append(Finding(secret_name, "shadows-values-entry",
                                    f"{parsed.name} is also a values entry; the Secret wins"))
            # Not a refusal — the cluster loads — but a silent shadow is how an operator edits the
            # values entry for an hour and wonders why nothing changes.
            failure(log, "secret-shadows-values", phase="parse", outcome="shadows-values-entry",
                    action="edit the Secret, or delete it to fall back to the values entry",
                    secret=secret_name, cluster=parsed.name,
                    detail="both declare this cluster; the Secret wins")
        if parsed.credential_kind == "oauth":
            findings.append(Finding(secret_name, "oauth-exchange-not-built",
                                    f"{parsed.name} declares oauth; the exchange is #119 P2 and the cluster is not polled"))
            failure(log, "credential-not-supported", phase="credential",
                    outcome="oauth-exchange-not-built", action=_ACTIONS["oauth-exchange-not-built"],
                    secret=secret_name, cluster=parsed.name, credential="oauth",
                    detail="the password-for-token exchange is not built; this cluster is not polled")
        clusters.append(parsed)
    return clusters, findings
