"""One discovery: LIST the labelled Secrets in the pod's namespace, parse each, apply the duplicate and
shadow rules (SPEC_S1 C2/C3). Raises ClusterError when the LIST itself fails — the caller records it as
the cycle's finding and keeps the previous set.

THIS FUNCTION DOES NOT LOG (review of #247, Grok C2). It ran every binding interval and knows nothing
about the cycle before it, so a `log.warning` per refused Secret here meant one standing bad Secret
wrote a line every cycle forever — the flood #245 exists to prevent. Findings are RETURNED; the
poller, which holds the previous cycle, announces the ones that appeared and the ones that cleared.
`_ACTIONS` and `finding_event` stay here because the fix, the event name and the phase belong beside
the code that knows the refusal.
"""

from __future__ import annotations

import dataclasses

from ..config import ClusterConfig
from . import LABEL_SELECTOR
from .parser import Finding, parse_secret
from .writer import TOKEN_SOURCE_ANNOTATION

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
    "visibility-invalid": "visibility must be inherit, self-only, hidden or remote-sar",
    "identity-invalid": "identity must be none or same-as-host, and remote-sar needs same-as-host",
    "enabled-invalid": 'enabled must be "true" or "false"',
    "host-cluster-not-from-secret": "the host cluster comes from the chart's values, not a Secret",
    "duplicate-cluster-name": "remove one of the two Secrets, or rename the cluster in one",
    "shadows-values-entry": "edit the Secret, or delete it to fall back to the values entry",
    "oauth-exchange-not-built": "use a bearerToken until the password exchange lands (#119 P2)",
}

#: How a finding is announced when it APPEARS (#245; the poller emits, this module decides): the
#: event name and the phase. The default is the parser's refusal, `secret-refused` at `parse`. Two
#: codes are not that: a shadowed values entry LOADS — the Secret wins, and the line exists so an
#: operator does not edit the values entry for an hour — and an oauth Secret parses cleanly and
#: stops one phase later, at the credential. Announcing either as a parse refusal would send the
#: reader to the wrong step of flow 1 (`docs/DESIGN_cluster_connection_flows.md`).
# `discovery-failed` is NOT here on purpose (second pass, OB3 N5): the registry synthesises that
# code for the tab, and the poller announces a failed LIST from its own site with its own phase and
# action — `finding_event("discovery-failed")` would answer `secret-refused`/`parse`, which is wrong,
# and no caller asks it. Route a discovery failure through `Poller._announce_discovery_failure`.
_EVENTS = {
    "shadows-values-entry": ("secret-shadows-values", "parse"),
    "oauth-exchange-not-built": ("credential-not-supported", "credential"),
}


def finding_event(code: str) -> tuple[str, str, str]:
    """The (event name, phase, action) a finding code is announced with."""
    name, phase = _EVENTS.get(code, ("secret-refused", "parse"))
    return name, phase, _ACTIONS.get(code, "see the Cluster Configurations tab")


def discover(cluster_client, namespace: str, *, host_name: str | None,
             values_names: tuple[str, ...] = (),
             values_modes: dict[str, str] | None = None) -> tuple[list[ClusterConfig], list[Finding]]:
    """`values_modes` maps a values entry's name to the credential kind its declared connection mode
    resolves to (`remote-lookup` / `self-login`, SPEC_S3 §3). A Secret over such an entry whose
    `token-source` annotation names that same kind is the retriever's own write (SPEC_S4 §1) — the
    Secret is MEANT to win there, so it is not a shadow finding. Any other shadow still is."""
    path = f"/api/v1/namespaces/{namespace}/secrets"
    with cluster_client._client() as client:
        items = cluster_client._list_all_with(client, path, {"labelSelector": LABEL_SELECTOR})
    # Deterministic: the findings list the same way every cycle.
    items.sort(key=lambda o: str((o.get("metadata") or {}).get("name") or ""))
    parsed_ok: list[ClusterConfig] = []
    findings: list[Finding] = []
    token_source: dict[str, str | None] = {}   # Secret name -> its token-source annotation, if any
    for obj in items:
        parsed = parse_secret(obj, host_name=host_name)
        if isinstance(parsed, Finding):
            findings.append(parsed)
            continue
        meta = obj.get("metadata") or {}
        token_source[str(meta.get("name") or "")] = (meta.get("annotations") or {}).get(TOKEN_SOURCE_ANNOTATION)
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
            continue
        parsed = group[0]
        secret_name = parsed.source.split(":", 1)[1]
        # The ownership the check below makes, recorded on the config itself (SPEC_D2b §3.4): the merge
        # serves a stanza's policy over the Secret the lookup wrote for it, and only that Secret.
        parsed = dataclasses.replace(parsed, token_source=token_source.get(secret_name))
        if parsed.name in values_names:
            # The retriever's own Secret over the stanza that asked for it is the design, not a
            # shadow (SPEC_S4 §1): the values entry declares the mode, the Secret says it came from it.
            ours = (values_modes or {}).get(parsed.name) is not None \
                and token_source.get(secret_name) == (values_modes or {}).get(parsed.name)
            if not ours:
                findings.append(Finding(secret_name, "shadows-values-entry",
                                        f"{parsed.name} is also a values entry; the Secret wins"))
        if parsed.credential_kind == "oauth":
            findings.append(Finding(secret_name, "oauth-exchange-not-built",
                                    f"{parsed.name} declares oauth; the exchange is #119 P2 and the cluster is not polled"))
        clusters.append(parsed)
    return clusters, findings
