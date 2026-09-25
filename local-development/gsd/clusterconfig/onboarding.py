"""SPEC_S5: ConfigMap intent -> existing lookup -> labelled Secret discovery.

Two complete, namespace-scoped inventories precede every mutation. No edge-triggered deletion
state: absent outputs are reconciled from the current inventory, including after a restart.
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import json

import httpx
import yaml

from ..config import ConfigError, parse_cluster_entries, remote_policy
from ..kube import ClusterError
from ..fleetlookup import LookupRefused, LookupSource, declared_trust
from . import CONFIG_SELECTOR, LABEL_SELECTOR
from .parser import Finding, _data, _NAME, parse_secret
from .reader import discover
from .writer import (
    MANAGED_BY_ANNOTATION, MANAGED_BY_ONBOARD,
    CreateRequest, WriteFailed, WriteRefused, onboarding_owner, reconcile_onboarding, secret_name_for, validate,
)


class _UniqueLoader(yaml.SafeLoader):
    """A duplicate YAML key must not silently erase a declaration or a credential refusal."""


def _mapping(loader, node, deep=False):
    loader.flatten_mapping(node)
    out = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in out:
            raise ValueError("mapping keys must be unique strings")
        out[key] = loader.construct_object(value_node, deep=deep)
    return out


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def _connection(cluster, settings, namespace):
    """Validate the eventual Secret before any login; hash connection inputs, excluding policy."""
    tls, ca = declared_trust(cluster)
    request = CreateRequest(name=cluster.name, server=cluster.api_url, credential_kind="bearerToken",
                            token="validation-only", tls_mode=tls, ca_data=ca,
                            visibility=cluster.visibility or "remote-sar",
                            identity=cluster.identity or "same-as-host")
    # remote_policy handles identity:none alone, the same default used by the real lookup.
    request = dataclasses.replace(request, **dict(zip(("visibility", "identity"),
                                  remote_policy(cluster.visibility, cluster.identity))))
    parsed = validate(request, namespace, host_name=settings.host_cluster().name, taken={})
    if parsed.name != cluster.name:
        raise ValueError("cluster identity must survive Secret serialization unchanged")
    source = LookupSource.from_settings(settings)
    payload = [str(httpx.URL(cluster.api_url)), tls, ca, cluster.ldap_connection_bootstrap or settings.fleet_account_username,
               source.namespace, source.service_account, source.secret_name]
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def discover_onboarding(host_client, namespace: str, *, settings, mutate: bool):
    """Return clusters, findings, blocked names; an incomplete LIST raises without any mutation."""
    with host_client._client() as client:
        maps = host_client._list_all_with(client, f"/api/v1/namespaces/{namespace}/configmaps",
                                         {"labelSelector": CONFIG_SELECTOR})
        secrets = host_client._list_all_with(client, f"/api/v1/namespaces/{namespace}/secrets",
                                            {"labelSelector": LABEL_SELECTOR})
    host = settings.host_cluster()
    findings = []
    declarations = {}             # source -> ClusterConfig; invalid named entries still reserve a name
    authors = {}                  # cluster name -> source descriptions
    reserved = set()              # (ConfigMap name, UID, cluster name), also for invalid named entries
    uncertain = set()             # malformed whole documents: absence cannot prove removal
    for obj in sorted(maps, key=lambda o: o["metadata"]["name"]):
        meta = obj["metadata"]
        cm, uid = meta["name"], meta.get("uid", "")
        source = f"configmap:{cm}"
        try:
            data = obj.get("data") or {}
            if set(data) != {"clusters.yaml"} or obj.get("binaryData") or not uid:
                raise ValueError("requires data.clusters.yaml only and an API-assigned UID")
            raw = yaml.load(data["clusters.yaml"], Loader=_UniqueLoader)
            if not isinstance(raw, dict) or set(raw) != {"clusters"} or not isinstance(raw["clusters"], list):
                raise ValueError("requires a mapping containing only a clusters list")
            entries = raw["clusters"]
        except (yaml.YAMLError, ValueError, TypeError, RecursionError):
            uncertain.add(cm)
            findings.append(Finding(source, "onboarding-invalid",
                                    "ConfigMap (config-type onboard or sideload) needs data.clusters.yaml with a clusters list; "
                                    "unique keys, no extra data or binaryData; existing outputs are held, not polled"))
            continue
        for index, entry in enumerate(entries):
            source = f"configmap:{cm}:{index}"
            raw_name = entry.get("name") if isinstance(entry, dict) else None
            name = str(raw_name) if raw_name is not None else None  # same coercion as the values parser
            if isinstance(name, str) and _NAME.fullmatch(name):
                reserved.add((cm, uid, name))
            else:
                # Cannot identify which previous stanza this malformed entry replaced.
                uncertain.add(cm)
            try:
                cluster, = parse_cluster_entries([entry], source, remote_host=host)
                digest = _connection(cluster, settings, namespace)
            except (ConfigError, WriteRefused, LookupRefused, TypeError, ValueError, RecursionError):
                # Never echo values, YAML snippets, arbitrary keys or exception text from this feed.
                findings.append(Finding(source, "onboarding-invalid",
                                        "invalid values-shaped stanza: check name/apiUrl, known keys, booleans, TLS and policy; "
                                        "use saTokenLookup: true, no credential or token reference, and no host declaration"))
                continue
            authors.setdefault(cluster.name, []).append(source)
            declarations[source] = dataclasses.replace(cluster, source=source, onboarding=(cm, uid, digest))

    # Values/ConfigMap duplicates load neither. Protect the values host before considering duplicates.
    for cluster in settings.clusters:
        if cluster.name in authors:
            authors[cluster.name].append("values")
    outputs = {}
    ordinary = []
    for obj in secrets:
        meta = obj.get("metadata") or {}
        data, _ = _data(obj)
        name = data.get("name", "").strip()
        owner = onboarding_owner(obj)
        if owner is not None:
            outputs[meta["name"]] = (obj, owner, name)
        elif (meta.get("annotations") or {}).get(MANAGED_BY_ANNOTATION) == MANAGED_BY_ONBOARD:
            findings.append(Finding(meta["name"], "onboarding-ownership-conflict",
                                    "generated Secret ownership is incomplete or changed; left untouched and not polled"))
            if name in authors:
                authors[name].append(f"secret:{meta['name']}")
        else:
            ordinary.append(obj)
            if name in authors:
                authors[name].append(f"secret:{meta['name']}")
    blocked = {name for name, sources in authors.items() if len(sources) > 1}
    for name in sorted(blocked):
        for source in authors[name]:
            findings.append(Finding(source, "duplicate-cluster-name",
                                    f"{name} is declared by {', '.join(authors[name])}; none loads until the conflict is removed"))
    desired = {c.name: c for c in declarations.values() if c.name not in blocked}
    ready = []
    pending = dict(desired)
    writable = mutate and settings.cluster_secrets_enabled and settings.cluster_secrets_writes_enabled
    for secret_name, (obj, owner, name) in sorted(outputs.items()):
        cluster = desired.get(name)
        declared = (owner[0], owner[1], name) in reserved
        if name in blocked or owner[0] in uncertain or (declared and cluster is None):
            findings.append(Finding(secret_name, "onboarding-cleanup-pending",
                                    "source is malformed or conflicted; credential retained, not polled; fix its ConfigMap"))
            pending.pop(name, None)
            continue
        matching = cluster is not None and owner == cluster.onboarding
        parsed = parse_secret(obj, host_name=host.name)
        if matching and not isinstance(parsed, Finding):
            tls, ca = declared_trust(cluster)
            matching = (httpx.URL(parsed.api_url) == httpx.URL(cluster.api_url) and parsed.credential_kind == "bearer"
                        and parsed.insecure_skip_verify == (tls == "insecure")
                        and parsed.ca_data == (base64.b64decode(ca).decode() if ca else None))
        elif matching:
            matching = False
        if not matching:
            # Complete inventory proves displacement, or credential/connection data drifted.
            if not writable:
                findings.append(Finding(secret_name, "onboarding-cleanup-pending",
                                        "generated credential is displaced; cleanup requires a single leader and "
                                        "clusterConfig.secrets.writes.enabled; not polled"))
                pending.pop(name, None)
                continue
            try:
                reconcile_onboarding(host_client, namespace, obj)
            except (WriteFailed, WriteRefused):
                findings.append(Finding(secret_name, "onboarding-cleanup-pending",
                                        "generated Secret cleanup failed or ownership changed; retained, not polled; retried next cycle"))
                pending.pop(name, None)
            # Successful delete is still observed in this snapshot: creation waits for a fresh LIST.
            else:
                pending.pop(name, None)
            continue
        # Same connection: policy edits consume no credential and never log in.
        if writable:
            try:
                obj = reconcile_onboarding(host_client, namespace, obj, desired=cluster)
            except (WriteFailed, WriteRefused):
                findings.append(Finding(secret_name, "lookup-write-failed",
                                        "generated Secret policy update failed; declared policy is served; retried next cycle"))
        ready.append(obj)
        pending.pop(name, None)
    # A current declaration whose output is missing is handed to the EXISTING lookup scheduler.
    ordinary = [o for o in ordinary if _data(o)[0].get("name", "").strip() not in blocked]
    clusters, secret_findings = discover(host_client, namespace, host_name=host.name,
                                        values_names=tuple(c.name for c in settings.clusters),
                                        values_modes={c.name: c.credential_kind for c in settings.clusters if c.connection_mode},
                                        items=ordinary + ready)
    findings.extend(secret_findings)
    for i, cluster in enumerate(clusters):
        declaration = desired.get(cluster.name)
        if declaration is not None and cluster.source.split(":", 1)[-1] in outputs:
            clusters[i] = dataclasses.replace(cluster, enabled=declaration.enabled,
                                              visibility=declaration.visibility, identity=declaration.identity,
                                              onboarding=declaration.onboarding)
    # Detect a physical-name collision, including an unlabelled Secret, before spending a login.
    for name, cluster in list(pending.items()):
        with host_client._client() as client:
            try:
                host_client._get(client, f"/api/v1/namespaces/{namespace}/secrets/{secret_name_for(name)}", {})
            except ClusterError as exc:
                if exc.message.startswith("HTTP 404"):
                    continue
                detail = "cannot establish that the output Secret name is free; no lookup attempted"
            else:
                detail = "output Secret already exists and is not this declaration's accepted output; left untouched"
        pending.pop(name)
        findings.append(Finding(cluster.source, "onboarding-ownership-conflict", detail))
    clusters.extend(pending.values())
    return clusters, findings, blocked
