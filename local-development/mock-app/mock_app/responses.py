"""Kubernetes List/object envelope builders + the exact per-item JSON shapes kube.py parses.

Every builder here emits the nesting DESIGN §3 lists and that kube.py's ``_groupsync_view`` /
``_group_view`` / ``_binding_views`` / ``_user_binding_views`` and the ``fetch_*`` methods read:
``metadata.labels`` / ``metadata.annotations`` are objects, ``users`` and ``identities`` are
TOP-LEVEL arrays on Group/User, ``status.conditions`` under ``status``, ``roleRef`` + ``subjects``
on bindings. Missing optional fields are simply omitted — kube.py uses ``(x or {})`` / ``.get``.
"""

from __future__ import annotations

from typing import Any

from .fixture import (
    Binding,
    Condition,
    GroupCR,
    GroupSyncCR,
    IdentityCR,
    NamespaceCR,
    NodeCR,
    OAuthCR,
    UserCR,
)

# Sync-operator / RBAC label + annotation keys, copied verbatim from gsd/kube.py so an item
# lands in exactly the field the parser reads.
SYNC_PROVIDER_LABEL = "group-sync-operator.redhat-cop.io/sync-provider"
SYNC_TIME_ANNOTATION = "group-sync-operator.redhat-cop.io/sync-time"
LDAP_UID_ANNOTATION = "openshift.io/ldap.uid"
CLIFF_SILENCE_ANNOTATION = "groupsync-dashboard.io/silence-group-count-cliff"
CONFIG_SOURCE_LABEL = "rbac.ocp.io/config-source"
UNMANAGED_LABEL = "rbac.ocp.io/unmanaged"
UNMANAGED_EXCEPTION_ANNOTATION = "rbac.ocp.io/unmanaged-exception"


# ── Envelope + paging ─────────────────────────────────────────────────────────────────────


# The real apiVersion each List envelope carries (review #118 C4). gsd.kube ignores the envelope
# version today, but a faithful mock must not emit a literal "unknown" — a future consumer that reads
# it, or a copy of a real capture, would diverge.
_LIST_API_VERSIONS = {
    "List": "v1", "NamespaceList": "v1", "NodeList": "v1", "PodList": "v1",
    "GroupSyncList": "redhatcop.redhat.io/v1alpha1",
    "NamespaceConfigList": "redhatcop.redhat.io/v1alpha1",
    "GroupConfigList": "redhatcop.redhat.io/v1alpha1",
    "GroupList": "user.openshift.io/v1", "UserList": "user.openshift.io/v1",
    "IdentityList": "user.openshift.io/v1",
    "RoleBindingList": "rbac.authorization.k8s.io/v1",
    "ClusterRoleBindingList": "rbac.authorization.k8s.io/v1",
}


def k8s_list(items: list[dict], kind: str = "List", continue_token: str | None = None) -> dict:
    """A Kubernetes List envelope. ``items`` is ALWAYS present (kube.py rejects a 200 without it).

    ``metadata.continue`` is emitted only when there is a next page; kube.py stops paging on a
    falsy/absent continue token.
    """
    metadata: dict[str, Any] = {}
    if continue_token:
        metadata["continue"] = continue_token
    try:
        api_version = _LIST_API_VERSIONS[kind]
    except KeyError as exc:      # a List kind with no known group is a fixture/wiring bug, fail loud
        raise ValueError(f"unknown Kubernetes List kind {kind!r}") from exc
    return {
        "apiVersion": api_version,
        "kind": kind,
        "metadata": metadata,
        "items": items,
    }


def paginate(items: list[dict], limit: int, cursor: str | None) -> tuple[list[dict], str | None]:
    """Slice ``items`` by an opaque offset cursor honouring ``limit`` (kube.py sends limit=500).

    The continue token is simply the next start offset as a string — opaque to the client,
    which echoes it back verbatim. Returns ``(page, next_cursor_or_None)``.
    """
    try:
        start = int(cursor) if cursor else 0
    except (TypeError, ValueError):
        start = 0
    if start < 0:
        start = 0
    if limit <= 0:
        limit = len(items)
    end = start + limit
    page = items[start:end]
    next_cursor = str(end) if end < len(items) else None
    return page, next_cursor


# ── Per-item builders ─────────────────────────────────────────────────────────────────────


def _conditions(conditions: tuple[Condition, ...]) -> list[dict]:
    out: list[dict] = []
    for c in conditions:
        entry: dict[str, Any] = {"type": c.type}
        if c.lastTransitionTime is not None:
            entry["lastTransitionTime"] = c.lastTransitionTime
        if c.message is not None:
            entry["message"] = c.message
        if c.observedGeneration is not None:
            entry["observedGeneration"] = c.observedGeneration
        out.append(entry)
    return out


def groupsync_item(cr: GroupSyncCR) -> dict:
    meta: dict[str, Any] = {"name": cr.name, "namespace": cr.namespace}
    if cr.generation is not None:
        meta["generation"] = cr.generation

    providers: list[dict] = []
    for p in cr.providers:
        entry: dict[str, Any] = {"name": p.name}
        if p.filter is not None:
            # kube.py's _ldap_filter reads spec.providers[].ldap.<scheme>.groupsQuery.filter.
            entry["ldap"] = {p.kind: {"groupsQuery": {"filter": p.filter}}}
        providers.append(entry)

    spec: dict[str, Any] = {"providers": providers}
    if cr.schedule is not None:
        spec["schedule"] = cr.schedule

    status: dict[str, Any] = {"conditions": _conditions(cr.conditions)}
    if cr.lastSyncSuccessTime is not None:
        status["lastSyncSuccessTime"] = cr.lastSyncSuccessTime

    return {"apiVersion": "redhatcop.redhat.io/v1alpha1", "kind": "GroupSync",
            "metadata": meta, "spec": spec, "status": status}


def group_item(cr: GroupCR) -> dict:
    labels: dict[str, str] = {}
    if cr.sync_provider is not None:
        labels[SYNC_PROVIDER_LABEL] = cr.sync_provider
    annotations: dict[str, str] = {}
    if cr.sync_time is not None:
        annotations[SYNC_TIME_ANNOTATION] = cr.sync_time
    if cr.ldap_uid is not None:
        annotations[LDAP_UID_ANNOTATION] = cr.ldap_uid
    if cr.cliff_silence is not None:
        annotations[CLIFF_SILENCE_ANNOTATION] = cr.cliff_silence

    meta: dict[str, Any] = {"name": cr.name}
    if labels:
        meta["labels"] = labels
    if annotations:
        meta["annotations"] = annotations

    # `users` is TOP-LEVEL on Group and is null (not []) for an empty group — kube.py reads
    # `obj.get("users") or []` and specifically documents the null case.
    users = None if cr.users is None else list(cr.users)
    return {"apiVersion": "user.openshift.io/v1", "kind": "Group",
            "metadata": meta, "users": users}


def user_item(cr: UserCR) -> dict:
    meta: dict[str, Any] = {"name": cr.name}
    if cr.creationTimestamp is not None:
        meta["creationTimestamp"] = cr.creationTimestamp
    item: dict[str, Any] = {
        "apiVersion": "user.openshift.io/v1",
        "kind": "User",
        "metadata": meta,
        # `identities` is TOP-LEVEL on User; `fullName` is a top-level string.
        "identities": list(cr.identities),
    }
    if cr.full_name is not None:
        item["fullName"] = cr.full_name
    return item


def identity_item(cr: IdentityCR) -> dict:
    meta: dict[str, Any] = {}
    if cr.creationTimestamp is not None:
        meta["creationTimestamp"] = cr.creationTimestamp
    provider = cr.provider_prefix or "mock-idp"
    return {
        "apiVersion": "user.openshift.io/v1",
        "kind": "Identity",
        "metadata": meta,
        "providerName": provider,
        # kube.py reads obj["user"]["name"].
        "user": {"name": cr.user_name},
    }


def namespace_item(cr: NamespaceCR) -> dict:
    meta: dict[str, Any] = {"name": cr.name}
    if cr.creationTimestamp is not None:
        meta["creationTimestamp"] = cr.creationTimestamp
    if cr.labels:
        meta["labels"] = dict(cr.labels)
    return {"apiVersion": "v1", "kind": "Namespace",
            "metadata": meta, "status": {"phase": cr.phase}}


def node_item(cr: NodeCR) -> dict:
    meta: dict[str, Any] = {"name": cr.name}
    if cr.labels:
        meta["labels"] = dict(cr.labels)
    return {"apiVersion": "v1", "kind": "Node", "metadata": meta}


def binding_item(b: Binding, kind: str) -> dict:
    """A RoleBinding or ClusterRoleBinding. ``kind`` is 'RoleBinding' | 'ClusterRoleBinding'."""
    meta: dict[str, Any] = {"name": b.name}
    if kind == "RoleBinding":
        meta["namespace"] = b.namespace
    if b.labels:
        meta["labels"] = dict(b.labels)
    if b.annotations:
        meta["annotations"] = dict(b.annotations)
    subjects: list[dict] = []
    for s in b.subjects:
        subj: dict[str, Any] = {"kind": s.kind, "name": s.name}
        if s.namespace:
            subj["namespace"] = s.namespace
        subjects.append(subj)
    return {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": kind,
        "metadata": meta,
        "roleRef": {
            "apiGroup": "rbac.authorization.k8s.io",
            "kind": b.role_ref.kind,
            "name": b.role_ref.name,
        },
        "subjects": subjects,
    }


def operator_config_item(name: str, conditions: tuple[Condition, ...], kind: str) -> dict:
    return {
        "apiVersion": "redhatcop.redhat.io/v1alpha1",
        "kind": kind,
        "metadata": {"name": name},
        "status": {"conditions": _conditions(conditions)},
    }


def oauth_object(oauth: OAuthCR) -> dict:
    """The OAuth CR — a plain object with spec.identityProviders, NOT a List (no items key)."""
    idps: list[dict] = []
    for p in oauth.identity_providers:
        entry: dict[str, Any] = {"name": p.name}
        if p.ldap_url is not None:
            entry["type"] = "LDAP"
            entry["ldap"] = {"url": p.ldap_url}
        idps.append(entry)
    return {
        "apiVersion": "config.openshift.io/v1",
        "kind": "OAuth",
        "metadata": {"name": "cluster"},
        "spec": {"identityProviders": idps},
    }


def pod_item(name: str, phase: str) -> dict:
    return {"apiVersion": "v1", "kind": "Pod",
            "metadata": {"name": name}, "status": {"phase": phase}}


def status_json(code: int, reason: str, message: str) -> dict:
    """A Kubernetes Status body (what a real API server returns on an error).

    Read by kube.py's _log_read_refused (``.reason``, ``.message``) on a pod-log >=400.
    """
    return {
        "apiVersion": "v1",
        "kind": "Status",
        "status": "Failure",
        "reason": reason,
        "message": message,
        "code": code,
    }
