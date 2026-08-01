"""Read-only Kubernetes/OpenShift REST client.

Two list calls per cluster per poll (PLAN §6), no watch. The client is deliberately thin —
raw REST over httpx rather than a generated client — because the only two resources needed
are a CRD and an OpenShift type, and both are simple to read directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from .config import ClusterConfig, ConfigError

log = logging.getLogger(__name__)

GROUPSYNC_API = "/apis/redhatcop.redhat.io/v1alpha1/groupsyncs"
"""Note: the API group is `redhatcop.redhat.io` (no hyphen after `redhat`), while the
labels and annotations the operator writes use `redhat-cop.io` (hyphenated). The two are
one character apart and transposing them yields a 404 that looks like a missing CRD."""

GROUP_API = "/apis/user.openshift.io/v1/groups"
ROLEBINDING_API = "/apis/rbac.authorization.k8s.io/v1/rolebindings"
CLUSTERROLEBINDING_API = "/apis/rbac.authorization.k8s.io/v1/clusterrolebindings"

SYSTEM_GROUP_PREFIX = "system:"
"""Kubernetes reserves this prefix for built-in identities.

Binding subjects like ``system:serviceaccounts:<ns>`` and ``system:authenticated`` are
VIRTUAL groups: they authorise real access but no Group object exists or ever will. On the
target cluster 110 of 149 distinct Group subjects are of this form, so treating "absent
from the Group API" as broken would bury the 9 genuinely broken ones in 110 false
positives. Reserved-by-convention rather than guaranteed, so these are classified and
labelled, never silently dropped."""

SYNC_PROVIDER_LABEL = "group-sync-operator.redhat-cop.io/sync-provider"
SYNC_TIME_ANNOTATION = "group-sync-operator.redhat-cop.io/sync-time"
LDAP_UID_ANNOTATION = "openshift.io/ldap.uid"

PAGE_SIZE = 500

# PLAN §12 step 7: these must stay distinguishable. A ServiceAccount that can list
# GroupSync but not Group produces a half-populated view that otherwise looks exactly like
# a cluster that simply has no groups.
OK = "ok"
AUTH_FAILED = "auth_failed"
FORBIDDEN = "forbidden"
UNREACHABLE = "unreachable"


class ClusterError(Exception):
    """A poll failed in a way that must be surfaced on the cluster card, not swallowed."""

    def __init__(self, outcome: str, message: str):
        super().__init__(message)
        self.outcome = outcome
        self.message = message


@dataclass
class GroupSyncView:
    """The fields of a GroupSync CR the dashboard reads (PLAN §3)."""

    name: str
    namespace: str
    schedule: str | None
    ldap_filter: str | None
    last_sync_at: str | None
    generation: int | None
    error_at: str | None
    error_message: str | None
    error_generation: int | None
    success_at: str | None


@dataclass
class GroupView:
    """The fields of a Group the dashboard reads (PLAN §3)."""

    name: str
    member_count: int
    sync_provider: str | None
    group_synced_at: str | None
    ldap_uid: str | None
    members: list[str]
    """The usernames themselves, not just the count.

    A count answers "is this group empty?"; only the names answer "why does this person have
    access?" — which is the question an operator actually arrives with."""


@dataclass
class BindingView:
    """One (binding, Group subject) pair.

    Flattened per subject rather than per binding: a binding naming three groups is three
    rows, which is the shape both drill-downs read it in ("which bindings name THIS
    group?"). Only ``kind: Group`` subjects are kept — User and ServiceAccount subjects
    cannot contribute to a user's access-via-groups, which is the question being answered.
    """

    binding_kind: str          # RoleBinding | ClusterRoleBinding
    binding_namespace: str     # "" for ClusterRoleBinding
    binding_name: str
    role_kind: str             # Role | ClusterRole
    role_name: str
    group_name: str

    @property
    def is_system_group(self) -> bool:
        return self.group_name.startswith(SYSTEM_GROUP_PREFIX)


class ClusterClient:
    """Talks to one cluster. One instance per cluster, reused across polls."""

    def __init__(self, cluster: ClusterConfig, timeout: float = 15.0):
        self.cluster = cluster
        self._timeout = timeout

    def _get(self, client: httpx.Client, path: str, params: dict[str, Any]) -> dict:
        try:
            response = client.get(path, params=params)
        except httpx.HTTPError as exc:
            # Connect errors, TLS failures and timeouts are all "we could not talk to it",
            # which is operationally different from "it said no".
            raise ClusterError(UNREACHABLE, f"{type(exc).__name__}: {exc}") from exc

        if response.status_code == 401:
            raise ClusterError(AUTH_FAILED, "401 Unauthorized — token invalid or expired")
        if response.status_code == 403:
            raise ClusterError(
                FORBIDDEN,
                f"403 Forbidden on {path} — the ServiceAccount lacks list permission here",
            )
        if response.status_code >= 400:
            raise ClusterError(
                UNREACHABLE, f"HTTP {response.status_code} on {path}: {response.text[:200]}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise ClusterError(UNREACHABLE, f"non-JSON response from {path}: {exc}") from exc

    def _list_all(self, client: httpx.Client, path: str) -> list[dict]:
        """List every object, following the API server's continue tokens.

        Paging is not optional. The API server returned a continue token for as few as two
        Groups when a limit was set, and a cluster with more groups than one response holds
        would otherwise be silently truncated — which looks identical to a cluster that has
        fewer groups than it really does, the exact failure class this dashboard exists to
        catch.
        """
        items: list[dict] = []
        params: dict[str, Any] = {"limit": PAGE_SIZE}
        while True:
            payload = self._get(client, path, params)
            items.extend(payload.get("items") or [])
            token = (payload.get("metadata") or {}).get("continue")
            if not token:
                return items
            params = {"limit": PAGE_SIZE, "continue": token}

    def _client(self) -> httpx.Client:
        try:
            token = self.cluster.resolve_token()
        except ConfigError as exc:
            raise ClusterError(AUTH_FAILED, str(exc)) from exc
        try:
            verify = self.cluster.verify()
        except ConfigError as exc:
            # An unreadable CA bundle is a local misconfiguration, not a rejection by the
            # cluster — reporting it as auth_failed would send someone hunting for a bad
            # token that is fine.
            raise ClusterError(UNREACHABLE, str(exc)) from exc
        return httpx.Client(
            base_url=self.cluster.api_url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            verify=verify,
            timeout=self._timeout,
        )

    def fetch(self) -> tuple[list[GroupSyncView], list[GroupView]]:
        """One poll's worth of reads. Raises ClusterError with a classified outcome."""
        with self._client() as client:
            groupsyncs = [_groupsync_view(o) for o in self._list_all(client, GROUPSYNC_API)]
            groups = [_group_view(o) for o in self._list_all(client, GROUP_API)]
        return groupsyncs, groups

    def fetch_bindings(self) -> list[BindingView]:
        """Every RoleBinding and ClusterRoleBinding subject of kind Group.

        Separate from fetch() and on its own slower cadence: this lists bindings across
        every namespace, which is far more expensive than the two list calls above, and
        bindings change on administrative action rather than on a sync schedule.
        """
        out: list[BindingView] = []
        with self._client() as client:
            for obj in self._list_all(client, ROLEBINDING_API):
                out.extend(_binding_views(obj, "RoleBinding"))
            for obj in self._list_all(client, CLUSTERROLEBINDING_API):
                out.extend(_binding_views(obj, "ClusterRoleBinding"))
        log.debug("fetched %d group-subject binding rows from %s", len(out), self.cluster.name)
        return out


def _condition(obj: dict, wanted: str) -> dict | None:
    for condition in (obj.get("status") or {}).get("conditions") or []:
        if condition.get("type") == wanted:
            return condition
    return None


def _groupsync_view(obj: dict) -> GroupSyncView:
    meta = obj.get("metadata") or {}
    spec = obj.get("spec") or {}
    status = obj.get("status") or {}

    error = _condition(obj, "ReconcileError")
    success = _condition(obj, "ReconcileSuccess")

    return GroupSyncView(
        name=meta.get("name", ""),
        namespace=meta.get("namespace", ""),
        schedule=spec.get("schedule"),
        ldap_filter=_ldap_filter(spec),
        last_sync_at=status.get("lastSyncSuccessTime"),
        generation=meta.get("generation"),
        # Kept even when stale: it is the only failure record the API retains, and it
        # outlives the operator pod restarts that lose the log (PLAN §2.1). Whether it is
        # *current* is decided in state.reconcile_error_is_current, never here.
        error_at=(error or {}).get("lastTransitionTime"),
        error_message=(error or {}).get("message"),
        error_generation=(error or {}).get("observedGeneration"),
        success_at=(success or {}).get("lastTransitionTime"),
    )


def _ldap_filter(spec: dict) -> str | None:
    """First provider's group query filter, for display on the detail page.

    Only the first provider is shown: the CRs in use carry exactly one, and rendering a
    merged filter across several would misrepresent which one produced a given group.
    """
    for provider in spec.get("providers") or []:
        ldap = provider.get("ldap") or {}
        for scheme in ("rfc2307", "activeDirectory", "augmentedActiveDirectory"):
            query = (ldap.get(scheme) or {}).get("groupsQuery") or {}
            if query.get("filter"):
                return query["filter"]
    return None


def _binding_views(obj: dict, binding_kind: str) -> list[BindingView]:
    """Flatten one binding into a row per Group subject.

    Subject matching is on ``kind`` exactly. A binding with no Group subject contributes
    nothing, which is why 530 RoleBindings on the target cluster reduce to 178 rows.
    """
    meta = obj.get("metadata") or {}
    role_ref = obj.get("roleRef") or {}
    rows: list[BindingView] = []
    for subject in obj.get("subjects") or []:
        if subject.get("kind") != "Group" or not subject.get("name"):
            continue
        rows.append(
            BindingView(
                binding_kind=binding_kind,
                # ClusterRoleBindings have no namespace; "" rather than None so it can sit
                # in a NOT NULL primary key column without a sentinel row per binding.
                binding_namespace=meta.get("namespace", "") or "",
                binding_name=meta.get("name", ""),
                role_kind=role_ref.get("kind", ""),
                role_name=role_ref.get("name", ""),
                group_name=subject["name"],
            )
        )
    return rows


def _group_view(obj: dict) -> GroupView:
    meta = obj.get("metadata") or {}
    labels = meta.get("labels") or {}
    annotations = meta.get("annotations") or {}
    # `users` is a top-level field on Group, not under spec, and is null rather than []
    # when the group is empty — which is precisely the EMPTY state of PLAN §7.
    users = obj.get("users") or []
    # Sorted so a membership diff between polls reflects real change, not API ordering.
    members = sorted(str(u) for u in users)
    return GroupView(
        name=meta.get("name", ""),
        member_count=len(members),
        sync_provider=labels.get(SYNC_PROVIDER_LABEL),
        group_synced_at=annotations.get(SYNC_TIME_ANNOTATION),
        ldap_uid=annotations.get(LDAP_UID_ANNOTATION),
        members=members,
    )
