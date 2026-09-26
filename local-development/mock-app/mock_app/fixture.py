"""The declarative fixture — the single source of truth for every endpoint.

One YAML (JSON accepted) file compiles into frozen dataclasses so the router, the SAR
authorizer and the audit server never touch raw dicts. Unknown top-level keys are rejected
(fail-loud): a typo in the fixture must not silently serve an empty cluster. Missing keys
default to empty collections / an empty OAuth CR.

Every shape here is authored to satisfy the parse contract in DESIGN §3 — see ``responses.py``
for the exact JSON envelopes and ``sar.py`` for how the RBAC graph is evaluated.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class FixtureError(ValueError):
    """The fixture file is malformed — raised at load time, never at request time."""


# ── Per-resource dataclasses ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Provider:
    name: str
    kind: str = "rfc2307"            # rfc2307 | activeDirectory | augmentedActiveDirectory
    filter: str | None = None


@dataclass(frozen=True)
class Condition:
    type: str                        # ReconcileError | ReconcileSuccess
    lastTransitionTime: str | None = None
    message: str | None = None
    observedGeneration: int | None = None


@dataclass(frozen=True)
class GroupSyncCR:
    name: str
    namespace: str = ""
    generation: int | None = None
    schedule: str | None = None
    providers: tuple[Provider, ...] = ()
    lastSyncSuccessTime: str | None = None
    conditions: tuple[Condition, ...] = ()


@dataclass(frozen=True)
class GroupCR:
    name: str
    users: tuple[str, ...] | None = None      # None → the API's `users: null` (empty group)
    sync_provider: str | None = None
    sync_time: str | None = None
    ldap_uid: str | None = None
    cliff_silence: str | None = None


@dataclass(frozen=True)
class UserCR:
    name: str
    full_name: str | None = None
    creationTimestamp: str | None = None
    identities: tuple[str, ...] = ()


@dataclass(frozen=True)
class IdentityCR:
    user_name: str
    creationTimestamp: str | None = None      # ISO-8601 required or kube.py drops the item
    provider_prefix: str | None = None


@dataclass(frozen=True)
class NamespaceCR:
    name: str
    phase: str = "Active"
    creationTimestamp: str | None = None
    labels: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class NodeCR:
    name: str
    labels: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Rule:
    verbs: tuple[str, ...]
    apiGroups: tuple[str, ...]
    resources: tuple[str, ...]
    resourceNames: tuple[str, ...] = ()


@dataclass(frozen=True)
class Role:
    name: str
    rules: tuple[Rule, ...] = ()
    namespace: str = ""              # "" → ClusterRole


@dataclass(frozen=True)
class Subject:
    kind: str                        # Group | User | ServiceAccount
    name: str
    namespace: str = ""


@dataclass(frozen=True)
class RoleRef:
    kind: str                        # Role | ClusterRole
    name: str


@dataclass(frozen=True)
class Binding:
    name: str
    role_ref: RoleRef
    subjects: tuple[Subject, ...] = ()
    namespace: str = ""              # "" → ClusterRoleBinding
    labels: dict[str, str] = field(default_factory=dict)
    annotations: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class OperatorConfigCR:
    name: str
    conditions: tuple[Condition, ...] = ()


@dataclass(frozen=True)
class IdentityProvider:
    name: str
    ldap_url: str | None = None


@dataclass(frozen=True)
class AuditLine:
    kind: str                        # credential | cli | session
    decision: str                    # allow | deny | error
    user: str
    at: str
    code: int = 302
    provider: str | None = None
    user_agent: str = "Mozilla/5.0"
    audit_id: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class AuditFile:
    name: str                        # audit.log | audit-<stamp>.log
    lines: tuple[AuditLine, ...] = ()


# ── Composite / feed wrappers ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Feed:
    """A list endpoint that can be flipped to a tolerated 403."""

    entries: tuple[Any, ...] = ()
    forbidden: bool = False


@dataclass(frozen=True)
class OperatorConfigs:
    namespace_configs: tuple[OperatorConfigCR, ...] = ()
    group_configs: tuple[OperatorConfigCR, ...] = ()
    namespace_configs_crd_absent: bool = False
    group_configs_crd_absent: bool = False


@dataclass(frozen=True)
class OAuthCR:
    identity_providers: tuple[IdentityProvider, ...] = ()
    forbidden: bool = False
    crd_absent: bool = False




@dataclass(frozen=True)
class AuditFixture:
    node: str = "master-0"
    directory: str = "oauth-server"
    files: tuple[AuditFile, ...] = ()
    malformed_416: bool = False       # emit a 416 with no Content-Range (exercise unranged retry)




@dataclass(frozen=True)
class Fixture:
    cluster_name: str
    token: str
    page_size: int | None
    groupsyncs: tuple[GroupSyncCR, ...]
    groupsyncs_crd_absent: bool
    groups: tuple[GroupCR, ...]
    users: Feed
    identities: Feed
    namespaces: Feed
    cluster_roles: tuple[Role, ...]
    namespaced_roles: tuple[Role, ...]
    cluster_role_bindings: tuple[Binding, ...]
    role_bindings: tuple[Binding, ...]
    operator_configs: OperatorConfigs
    nodes: Feed
    oauth: OAuthCR
    audit: AuditFixture
    source_path: str | None = None

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Fixture":
        raw = Path(path).read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise FixtureError(f"{path}: top level must be a mapping, got {type(data).__name__}")
        fx = cls.from_dict(data)
        object.__setattr__(fx, "source_path", str(path))
        return fx

    @classmethod
    def from_dict(cls, data: dict) -> "Fixture":
        allowed = {
            "meta", "groupsyncs", "groups", "users", "identities", "namespaces", "roles",
            "bindings", "operatorConfigs", "nodes", "oauth", "auditLog",
        }
        unknown = set(data) - allowed
        if unknown:
            raise FixtureError(
                f"unknown top-level fixture key(s): {', '.join(sorted(unknown))} "
                f"(allowed: {', '.join(sorted(allowed))})"
            )

        meta = _as_dict(data.get("meta"), "meta")
        cluster_name = meta.get("clusterName", "mock-openshift")
        token = meta.get("token", "mock-token")
        if not token:
            raise FixtureError("meta.token must be a non-empty string (the Bearer the gate requires)")
        page_size = meta.get("pageSize")
        if page_size is not None:
            if not isinstance(page_size, int) or page_size < 1:
                raise FixtureError("meta.pageSize must be a positive integer when set")

        groupsyncs_raw = data.get("groupsyncs") or []
        crd_absent = False
        gs_list = []
        for item in _as_list(groupsyncs_raw, "groupsyncs"):
            if not isinstance(item, dict):
                raise FixtureError("each groupsyncs entry must be a mapping")
            if "crdAbsent" in item:               # the flag may ride alongside entries or alone
                crd_absent = bool(item["crdAbsent"])
                if len(item) == 1:
                    continue
            gs_list.append(_group_sync(item))

        groups = tuple(_group(g) for g in _as_list(data.get("groups") or [], "groups"))
        users = _feed(data.get("users"), _user, "users")
        identities = _feed(data.get("identities"), _identity, "identities")
        namespaces = _feed(data.get("namespaces"), _namespace, "namespaces")
        cluster_roles, namespaced_roles = _roles(data.get("roles"))
        crbs, rbs = _bindings(data.get("bindings"))
        operator_configs = _operator_configs(data.get("operatorConfigs"))
        nodes = _feed(data.get("nodes"), _node, "nodes")
        oauth = _oauth(data.get("oauth"))
        audit = _audit(data.get("auditLog"))

        return cls(
            cluster_name=cluster_name,
            token=token,
            page_size=page_size,
            groupsyncs=tuple(gs_list),
            groupsyncs_crd_absent=crd_absent,
            groups=groups,
            users=users,
            identities=identities,
            namespaces=namespaces,
            cluster_roles=cluster_roles,
            namespaced_roles=namespaced_roles,
            cluster_role_bindings=crbs,
            role_bindings=rbs,
            operator_configs=operator_configs,
            nodes=nodes,
            oauth=oauth,
            audit=audit,
        )

    # Convenience the router/inspect page use.
    def summary(self) -> dict[str, Any]:
        return {
            "clusterName": self.cluster_name,
            "groupsyncs": len(self.groupsyncs),
            "groupsyncsCrdAbsent": self.groupsyncs_crd_absent,
            "groups": len(self.groups),
            "users": len(self.users.entries),
            "usersForbidden": self.users.forbidden,
            "identities": len(self.identities.entries),
            "namespaces": len(self.namespaces.entries),
            "clusterRoles": len(self.cluster_roles),
            "namespacedRoles": len(self.namespaced_roles),
            "clusterRoleBindings": len(self.cluster_role_bindings),
            "roleBindings": len(self.role_bindings),
            "nodes": len(self.nodes.entries),
            "oauthProviders": len(self.oauth.identity_providers),
            "auditNode": self.audit.node,
            "auditFiles": [f.name for f in self.audit.files],
        }


# ── Field compilers ──────────────────────────────────────────────────────────────────────────


def _as_dict(value: Any, where: str) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise FixtureError(f"{where} must be a mapping, got {type(value).__name__}")
    return value


def _as_list(value: Any, where: str) -> list:
    if value is None:
        return []
    if not isinstance(value, list):
        raise FixtureError(f"{where} must be a list, got {type(value).__name__}")
    return value


def _feed(value: Any, compile_one, where: str) -> Feed:
    block = _as_dict(value, where)
    entries = tuple(compile_one(e) for e in _as_list(block.get("entries") or [], f"{where}.entries"))
    return Feed(entries=entries, forbidden=bool(block.get("forbidden", False)))


def _conditions(raw: Any) -> tuple[Condition, ...]:
    out = []
    for c in _as_list(raw or [], "conditions"):
        out.append(Condition(
            type=c["type"],
            lastTransitionTime=c.get("lastTransitionTime"),
            message=c.get("message"),
            observedGeneration=c.get("observedGeneration"),
        ))
    return tuple(out)


def _group_sync(item: dict) -> GroupSyncCR:
    providers = tuple(
        Provider(name=p["name"], kind=p.get("kind", "rfc2307"), filter=p.get("filter"))
        for p in _as_list(item.get("providers") or [], "groupsyncs.providers")
    )
    return GroupSyncCR(
        name=item["name"],
        namespace=item.get("namespace", ""),
        generation=item.get("generation"),
        schedule=item.get("schedule"),
        providers=providers,
        lastSyncSuccessTime=item.get("lastSyncSuccessTime"),
        conditions=_conditions(item.get("conditions")),
    )


def _group(g: dict) -> GroupCR:
    users = g.get("users", None)
    if users is not None:
        users = tuple(str(u) for u in _as_list(users, "groups.users"))
    return GroupCR(
        name=g["name"],
        users=users,
        sync_provider=g.get("syncProvider"),
        sync_time=g.get("syncTime"),
        ldap_uid=g.get("ldapUid"),
        cliff_silence=g.get("cliffSilence"),
    )


def _user(u: dict) -> UserCR:
    return UserCR(
        name=u["name"],
        full_name=u.get("fullName"),
        creationTimestamp=u.get("creationTimestamp"),
        identities=tuple(u.get("identities") or ()),
    )


def _identity(i: dict) -> IdentityCR:
    return IdentityCR(
        user_name=i["userName"],
        creationTimestamp=i.get("creationTimestamp"),
        provider_prefix=i.get("providerPrefix"),
    )


def _namespace(n: dict) -> NamespaceCR:
    return NamespaceCR(
        name=n["name"],
        phase=n.get("phase", "Active"),
        creationTimestamp=n.get("creationTimestamp"),
        labels=dict(n.get("labels") or {}),
    )


def _node(n: dict) -> NodeCR:
    return NodeCR(name=n["name"], labels=dict(n.get("labels") or {}))


def _rule(r: dict) -> Rule:
    return Rule(
        verbs=tuple(r.get("verbs") or ()),
        apiGroups=tuple(r.get("apiGroups") or ()),
        resources=tuple(r.get("resources") or ()),
        resourceNames=tuple(r.get("resourceNames") or ()),
    )


def _roles(value: Any) -> tuple[tuple[Role, ...], tuple[Role, ...]]:
    block = _as_dict(value, "roles")
    cluster = tuple(
        Role(name=r["name"], rules=tuple(_rule(x) for x in _as_list(r.get("rules") or [], "rules")))
        for r in _as_list(block.get("clusterRoles") or [], "roles.clusterRoles")
    )
    namespaced = tuple(
        Role(
            name=r["name"],
            namespace=r["namespace"],
            rules=tuple(_rule(x) for x in _as_list(r.get("rules") or [], "rules")),
        )
        for r in _as_list(block.get("namespacedRoles") or [], "roles.namespacedRoles")
    )
    return cluster, namespaced


def _subjects(raw: Any) -> tuple[Subject, ...]:
    out = []
    for s in _as_list(raw or [], "subjects"):
        out.append(Subject(kind=s["kind"], name=s["name"], namespace=s.get("namespace", "")))
    return tuple(out)


def _binding(b: dict, namespace: str) -> Binding:
    ref = _as_dict(b.get("roleRef"), "roleRef")
    return Binding(
        name=b["name"],
        namespace=namespace,
        role_ref=RoleRef(kind=ref.get("kind", "ClusterRole"), name=ref["name"]),
        subjects=_subjects(b.get("subjects")),
        labels=dict(b.get("labels") or {}),
        annotations=dict(b.get("annotations") or {}),
    )


def _bindings(value: Any) -> tuple[tuple[Binding, ...], tuple[Binding, ...]]:
    block = _as_dict(value, "bindings")
    crbs = tuple(
        _binding(b, namespace="")
        for b in _as_list(block.get("clusterRoleBindings") or [], "bindings.clusterRoleBindings")
    )
    rbs = tuple(
        _binding(b, namespace=b["namespace"])
        for b in _as_list(block.get("roleBindings") or [], "bindings.roleBindings")
    )
    return crbs, rbs


def _operator_configs(value: Any) -> OperatorConfigs:
    block = _as_dict(value, "operatorConfigs")

    def one(c: dict) -> OperatorConfigCR:
        return OperatorConfigCR(name=c["name"], conditions=_conditions(c.get("conditions")))

    return OperatorConfigs(
        namespace_configs=tuple(
            one(c) for c in _as_list(block.get("namespaceConfigs") or [], "namespaceConfigs")
        ),
        group_configs=tuple(
            one(c) for c in _as_list(block.get("groupConfigs") or [], "groupConfigs")
        ),
        namespace_configs_crd_absent=bool(block.get("namespaceConfigsCrdAbsent", False)),
        group_configs_crd_absent=bool(block.get("groupConfigsCrdAbsent", False)),
    )


def _oauth(value: Any) -> OAuthCR:
    block = _as_dict(value, "oauth")
    idps = tuple(
        IdentityProvider(name=p["name"], ldap_url=p.get("ldapUrl"))
        for p in _as_list(block.get("identityProviders") or [], "oauth.identityProviders")
    )
    return OAuthCR(
        identity_providers=idps,
        forbidden=bool(block.get("forbidden", False)),
        crd_absent=bool(block.get("crdAbsent", False)),
    )




def _audit(value: Any) -> AuditFixture:
    block = _as_dict(value, "auditLog")
    files = []
    for f in _as_list(block.get("files") or [], "auditLog.files"):
        lines = tuple(
            AuditLine(
                kind=ln.get("kind", "credential"),
                decision=ln.get("decision", "allow"),
                user=ln["user"],
                at=ln["at"],
                code=int(ln.get("code", 302)),
                provider=ln.get("provider"),
                user_agent=ln.get("userAgent", "Mozilla/5.0"),
                audit_id=ln.get("auditId"),
                error_message=ln.get("errorMessage"),
            )
            for ln in _as_list(f.get("lines") or [], "auditLog.files.lines")
        )
        files.append(AuditFile(name=f["name"], lines=lines))
    return AuditFixture(
        node=block.get("node", "master-0"),
        directory=block.get("dir", "oauth-server"),
        files=tuple(files),
        malformed_416=bool(block.get("malformed416", False)),
    )




def load_fixture(path: str | Path) -> Fixture:
    """Load a fixture from a ``.yaml``/``.yml``/``.json`` file (YAML is a JSON superset)."""
    return Fixture.from_yaml(path)


__all__ = ["Fixture", "FixtureError", "load_fixture", "json"]
