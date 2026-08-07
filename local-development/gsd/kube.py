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

# The User objects themselves, read for ONE field: fullName.
#
# A User exists only once that person has authenticated — OpenShift creates it on first login and the
# identity provider fills fullName from its `attributes.name` mapping. Group membership does NOT create
# one: the group-sync operator writes LDAP uids into a Group's `users` array, and nothing about that
# implies the person has ever logged in. Measured on the reference cluster: 10 distinct group members,
# 7 with a User carrying a fullName, 3 with no User object at all — one of which (`hello1`) has no
# directory entry either, so it can never acquire one. Absence is therefore the normal case, not an
# error, and every consumer of this data has to render the bare id unchanged.
USER_API = "/apis/user.openshift.io/v1/users"

# The namespace-configuration-operator's CRs — SAME API group as GroupSync, different
# CRDs. Cluster-scoped. These template out the RoleBindings that grant the synced groups
# their access, so they are the other half of the pipeline this dashboard watches.
NAMESPACECONFIG_API = "/apis/redhatcop.redhat.io/v1alpha1/namespaceconfigs"
GROUPCONFIG_API = "/apis/redhatcop.redhat.io/v1alpha1/groupconfigs"
ROLEBINDING_API = "/apis/rbac.authorization.k8s.io/v1/rolebindings"
CLUSTERROLEBINDING_API = "/apis/rbac.authorization.k8s.io/v1/clusterrolebindings"

SYSTEM_GROUP_PREFIX = "system:"

# Platform identities that appear as `kind: User` on bindings the cluster ships with, and
# which must never be reported as a governance violation. Measured on the reference
# cluster: 36 direct-user bindings, of which 22 are these — kube-apiserver, kube-scheduler,
# kube-controller-manager, the node identities, and SA-shaped users like
# `system:serviceaccount:...`. Flagging them would bury the real findings under platform
# noise, which is the same mistake the `system:` GROUP tiering exists to avoid.
PLATFORM_USER_PREFIXES = ("system:",)
PLATFORM_USER_NAMES = frozenset({
    "kube-apiserver", "kubelet", "kube-controller-manager", "kube-scheduler", "kube-proxy",
    # kubeadmin is OpenShift's break-glass cluster identity, not a person with an LDAP
    # account. Flagging it as a migration violation is noise: there is nowhere to migrate
    # it TO, and on the reference cluster it accounted for 12 of the 14 non-system rows —
    # so leaving it in would have made the finding look like a kubeadmin report.
    "kubeadmin",
})


def is_platform_user(name: str) -> bool:
    """Whether a User subject is a cluster-internal identity rather than a person."""
    return name.startswith(PLATFORM_USER_PREFIXES) or name in PLATFORM_USER_NAMES
"""Kubernetes reserves this prefix for built-in identities.

Binding subjects like ``system:serviceaccounts:<ns>`` and ``system:authenticated`` are
VIRTUAL groups: they authorise real access but no Group object exists or ever will. On the
target cluster 110 of 149 distinct Group subjects are of this form, so treating "absent
from the Group API" as broken would bury the 9 genuinely broken ones in 110 false
positives. Reserved-by-convention rather than guaranteed, so these are classified and
labelled, never silently dropped."""

SYNC_PROVIDER_LABEL = "group-sync-operator.redhat-cop.io/sync-provider"
CONFIG_SOURCE_LABEL = "rbac.ocp.io/config-source"
UNMANAGED_EXCEPTION_ANNOTATION = "rbac.ocp.io/unmanaged-exception"

# READ, never written. The dashboard used to apply this label to its own findings; that
# write path was removed (see the comment above `class ClusterClient`), so the label now
# means "a human or a CI job acknowledged this finding" — a LABEL rather than an annotation
# precisely because it has to be selectable:
#
#     oc get rolebindings,clusterrolebindings -A -l rbac.ocp.io/unmanaged=true
#
# When a labelled object stops being a finding, the poller reports `unmanaged grant
# RESOLVED` so the stale acknowledgement can be cleaned up.
#
# The two `unmanaged-detected-at` / `-detected-by` annotations that accompanied the write
# were deleted with it: nothing wrote them and nothing read them.
UNMANAGED_LABEL = "rbac.ocp.io/unmanaged"
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
    provider_names: tuple[str, ...] = ()
    """The names the CR declares in spec.providers[].name.

    These make attribution EXACT. The operator labels each Group it creates with
    ``<groupsync-name>_<provider-name>``, so with the names in hand the expected label is
    reconstructible rather than guessed at by prefix — and prefix guessing is genuinely
    ambiguous: a CR named ``corp`` and a CR named ``corp_extra`` both match the label
    ``corp_extra_ldap``, so one group ends up with two owners, counted twice and
    staleness-checked twice.

    Empty for a CR whose spec declares no names, in which case poller.provider_keys_for
    falls back to prefix matching. See there.
    """


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
class UserBindingView:
    """A binding granting a role DIRECTLY to a User subject.

    The governance violation this dashboard exists to make visible, in its purest form: a
    grant tied to a person rather than to an enterprise-managed group. It survives
    offboarding — LDAP removing someone from a group revokes their access everywhere, while
    a direct binding keeps granting to a name nobody is watching — and it is invisible to
    every group-based review, including the rest of this dashboard.

    Kept separate from BindingView because the questions differ: that one asks "does this
    group exist?", this one asks "why is a person named here at all?".
    """

    binding_kind: str
    binding_namespace: str
    binding_name: str
    role_kind: str
    role_name: str
    user_name: str
    is_platform: bool
    """Cluster-internal identity (system:*, kube-apiserver, …) rather than a person.
    Carried rather than filtered out, so the UI can report the whole picture and the count
    of what it excluded — silently dropping rows is how a tool loses trust."""


@dataclass
class OperatorConfigView:
    """A NamespaceConfig or GroupConfig CR — reconcile health only, per the design scope.

    Deliberately NOT the spec templates: diffing "what bindings should exist" would mean
    re-implementing the operator's templating engine. These CRs have no schedule either,
    so unlike GroupSync there is no staleness to compute and no timeline worth keeping —
    the only question is "is its latest reconcile an error?", answered by the same sticky
    ReconcileError/ReconcileSuccess ordering trick GroupSync needs (the operator never
    clears ReconcileError; both conditions sit True forever)."""

    kind: str                # NamespaceConfig | GroupConfig
    name: str
    error_at: str | None
    error_message: str | None
    success_at: str | None


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
    managed_source: str | None = None
    """The provenance label value the policy operator stamps on bindings it templates
    (`rbac.ocp.io/config-source` by default). None means nothing manages this binding —
    somebody created it by hand, which is the `unmanaged` finding."""
    exception: str | None = None
    """The operator-acknowledged justification for an unmanaged binding, carried as an
    annotation ON the binding so the truth lives next to the object rather than in a
    dashboard-side allowlist. Suppresses the `unmanaged` finding."""
    audit_stamped: bool = False
    """Whether this binding already carries the dashboard's unmanaged audit label —
    the idempotency check, so a stamp is written once and never re-patched."""

    @property
    def is_system_group(self) -> bool:
        return self.group_name.startswith(SYSTEM_GROUP_PREFIX)


# NO WRITE METHOD ON THIS CLIENT, and that is the design rather than an omission.
#
# stamp_unmanaged_binding / unstamp_unmanaged_binding used to live here, patching a label and
# two annotations onto bindings the dashboard classified `unmanaged`. Both are gone with the
# RBAC grant that enabled them: Kubernetes privilege-escalation prevention refuses a patch on
# an RBAC object unless the writer already holds every permission that object grants, even for
# metadata. Measured on a live cluster — 4 planned, 0 landed, 175 extra rule sets demanded to
# label a binding granting nothing but `view`.
#
# The findings are published to the log, the UI and the API. Acknowledging one is a
# cluster-admin task on the object (`oc annotate ... rbac.ocp.io/unmanaged-exception=<why>`),
# which this client READS. git history has the removed code if a cluster ever justifies it.


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

            # A 200 whose body is not a Kubernetes List must NOT be read as "no objects".
            # `payload.get("items") or []` turns any unexpected 200 — a proxy error page, a
            # login redirect rendered as JSON, a truncated body — into an authoritative
            # empty result. The poll then deletes every group, records a departure for
            # every member into append-only history, and reports `ok`. Measured: one such
            # response wiped 60 groups and wrote 120 false "removed" events.
            #
            # An genuinely empty collection still has the key (`"items": []` or null), so
            # requiring its presence rejects malformed bodies without rejecting empty ones.
            if "items" not in payload:
                raise ClusterError(
                    UNREACHABLE,
                    f"{path} returned HTTP 200 without an 'items' field "
                    f"(kind={payload.get('kind')!r}) — refusing to treat this as an empty "
                    f"collection",
                )
            page = payload.get("items")
            if page is not None and not isinstance(page, list):
                raise ClusterError(
                    UNREACHABLE, f"{path} returned 'items' of type {type(page).__name__}"
                )
            items.extend(page or [])
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

    def fetch(self) -> tuple[list[GroupSyncView] | None, list[GroupView]]:
        """One poll's worth of reads. Raises ClusterError with a classified outcome.

        A MISSING GroupSync CRD IS NOT A POLL FAILURE. Reported from a real cluster that does
        not run the group-sync-operator: the dashboard warned that it could not detect the CRD
        and then showed no groups at all, when the hand-made Groups on that cluster should have
        appeared as `unattributed`.

        The cause was ordering plus an unhandled status. GroupSync is listed FIRST here, a 404
        on an absent CRD becomes `ClusterError(UNREACHABLE)` in `_get`, and `poll_once` catches
        that, records the cluster unreachable and returns — so `GROUP_API` was never called on a
        cluster without the operator. The dashboard's whole subject is groups; it must still
        report them when the operator that usually creates them is absent.

        Groups are therefore fetched even when the CRD is not installed, and with no CR to claim
        them every group has a NULL sync_provider, which is exactly the `unattributed` state.
        Same treatment `fetch_operator_configs` already gives the
        namespace-configuration-operator's CRDs.

        RETURNS None FOR THE CRs, NOT []. The absence must stay visible: `[]` would render as
        "GroupSync CRs: 0" on the Overview, indistinguishable from an installed operator with no
        CRs defined, and the only remaining signal would be a line in the pod log. None is
        carried to `replace_groupsync_state`, which records it, and `state.py` raises a
        `groupsync_crd_absent` alert from it.

        401 and 403 still propagate. "The CRD does not exist" and "the ServiceAccount may not
        read it" are different problems and only the first is a normal state.
        """
        with self._client() as client:
            try:
                groupsyncs = [_groupsync_view(o) for o in self._list_all(client, GROUPSYNC_API)]
            except ClusterError as exc:
                # Anchored on the path, not a bare "404" substring. The message ends with 200
                # characters of the response BODY, so a 500 whose body happens to mention 404
                # would otherwise be misread as "CRD absent" — hiding a real outage behind a
                # normal-looking state.
                if not exc.message.startswith(f"HTTP 404 on {GROUPSYNC_API}"):
                    raise
                log.warning(
                    "%s: no GroupSync CRD on this cluster, so the group-sync-operator is not "
                    "installed. Groups are still read and reported; with no CR to attribute "
                    "them to, every group shows as `unattributed`.",
                    self.cluster.name,
                )
                groupsyncs = None
            groups = [_group_view(o) for o in self._list_all(client, GROUP_API)]
        return groupsyncs, groups

    def fetch_user_bindings(self) -> list[UserBindingView]:
        """Every RoleBinding and ClusterRoleBinding subject of kind User.

        Rides the same cadence and the same two list calls' worth of data as
        fetch_bindings — bindings change on administrative action, not on a schedule.
        """
        out: list[UserBindingView] = []
        with self._client() as client:
            for obj in self._list_all(client, ROLEBINDING_API):
                out.extend(_user_binding_views(obj, "RoleBinding"))
            for obj in self._list_all(client, CLUSTERROLEBINDING_API):
                out.extend(_user_binding_views(obj, "ClusterRoleBinding"))
        log.debug("fetched %d direct-user binding rows from %s", len(out), self.cluster.name)
        return out

    def fetch_users(self) -> dict[str, str] | None:
        """Display names for users who have logged in, or None when we may not read them.

        One list call for one field. Keyed by username, and only names that are actually set:
        a User with no fullName is indistinguishable from no User at all as far as anything
        downstream is concerned, so it is left out rather than stored as an empty string.

        None means FORBIDDEN, and it is deliberately distinct from {} (allowed, nobody has a
        name yet). The grant is new: an install that upgrades the image without re-applying the
        chart's RBAC gets a 403 here, and that must not fail the poll or blank the names already
        known — so the caller skips its write and last cycle's names survive.

        Note the asymmetry with fetch(): there, swallowing a 403 would report a missing grant as
        a healthy operator-less cluster, which is the failure this dashboard exists to prevent
        applied to itself. Here the grant is optional by construction and the whole feature is
        cosmetic — a 403 costs display names, never correctness — so tolerating it is right in
        this one place and wrong in that one. Every other status still raises.
        """
        with self._client() as client:
            try:
                items = self._list_all(client, USER_API)
            except ClusterError as exc:
                # Anchored on the outcome AND the path. The outcome alone would be enough today
                # because this method calls exactly one path, but the pairing survives someone
                # adding a second call here later and not noticing that a 403 on it would be
                # read as "no permission on users".
                if exc.outcome == FORBIDDEN and USER_API in exc.message:
                    log.debug(
                        "%s: not permitted to list users — display names unavailable",
                        self.cluster.name,
                    )
                    return None
                raise
        names = {
            name: full
            for obj in items
            if (name := (obj.get("metadata") or {}).get("name"))
            and (full := (obj.get("fullName") or "").strip())
        }
        log.debug(
            "fetched %d users from %s, %d with a display name",
            len(items), self.cluster.name, len(names),
        )
        return names

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

    def fetch_operator_configs(self) -> list[OperatorConfigView] | None:
        """NamespaceConfig and GroupConfig health, or None when the operator is absent.

        AUTO-DETECTED, not configured: a 404 on the CRD path means the
        namespace-configuration-operator is not installed on this cluster, and that is a
        normal state rather than an error — most clusters running group-sync do not run
        it. None (absent) is deliberately distinct from [] (installed, zero CRs), because
        the UI must not render "0 configs, all healthy" on a cluster where the concept
        does not exist.
        """
        out: list[OperatorConfigView] = []
        any_crd_answered = False
        with self._client() as client:
            for path, kind in ((NAMESPACECONFIG_API, "NamespaceConfig"),
                               (GROUPCONFIG_API, "GroupConfig")):
                try:
                    items = self._list_all(client, path)
                except ClusterError as exc:
                    # Anchored on the path rather than a bare "404" substring: the message ends
                    # with 200 characters of the response BODY, so a 500 whose body mentions 404
                    # would be misread as "CRD absent" and would silently hide the operator's
                    # health instead of reporting it broken.
                    if exc.message.startswith(f"HTTP 404 on {path}"):
                        # This CRD is not installed. Tracked per-CRD rather than assumed
                        # pairwise: the operator ships both, but a cluster mid-install or
                        # with a pruned CRD is not a reason to lose the other's health.
                        log.debug("%s: %s CRD not present", self.cluster.name, kind)
                        continue
                    raise
                any_crd_answered = True
                for obj in items:
                    error = _condition(obj, "ReconcileError")
                    success = _condition(obj, "ReconcileSuccess")
                    out.append(OperatorConfigView(
                        kind=kind,
                        name=(obj.get("metadata") or {}).get("name", ""),
                        error_at=(error or {}).get("lastTransitionTime"),
                        error_message=(error or {}).get("message"),
                        success_at=(success or {}).get("lastTransitionTime"),
                    ))
        return out if any_crd_answered else None


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
        provider_names=_provider_names(spec),
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


def _provider_names(spec: dict) -> tuple[str, ...]:
    """The declared provider names, in order. Empty when the spec omits them."""
    return tuple(
        str(p["name"])
        for p in (spec.get("providers") or [])
        if isinstance(p, dict) and p.get("name")
    )


def _ldap_filter(spec: dict) -> str | None:
    """First provider's group query filter, for display on the detail page.

    Deliberately only the first, even though a CR may declare several: a merged filter would
    misrepresent which provider produced a given group, and the honest alternative — one
    filter per provider — needs the detail page to attribute each to its own label value.
    This is display only. Attribution and staleness use every provider (poller.provider_keys_for).
    """
    for provider in spec.get("providers") or []:
        ldap = provider.get("ldap") or {}
        for scheme in ("rfc2307", "activeDirectory", "augmentedActiveDirectory"):
            query = (ldap.get(scheme) or {}).get("groupsQuery") or {}
            if query.get("filter"):
                return query["filter"]
    return None


def _user_binding_views(obj: dict, binding_kind: str) -> list[UserBindingView]:
    """Flatten one binding into a row per User subject. Empty for the vast majority."""
    meta = obj.get("metadata") or {}
    role_ref = obj.get("roleRef") or {}
    rows: list[UserBindingView] = []
    for subject in obj.get("subjects") or []:
        if subject.get("kind") != "User" or not subject.get("name"):
            continue
        rows.append(
            UserBindingView(
                binding_kind=binding_kind,
                binding_namespace=meta.get("namespace", "") or "",
                binding_name=meta.get("name", ""),
                role_kind=role_ref.get("kind", ""),
                role_name=role_ref.get("name", ""),
                user_name=subject["name"],
                is_platform=is_platform_user(subject["name"]),
            )
        )
    return rows


def _binding_views(obj: dict, binding_kind: str) -> list[BindingView]:
    """Flatten one binding into a row per Group subject.

    Subject matching is on ``kind`` exactly. A binding with no Group subject contributes
    nothing, which is why 530 RoleBindings on the target cluster reduce to 178 rows.
    """
    meta = obj.get("metadata") or {}
    role_ref = obj.get("roleRef") or {}
    labels = meta.get("labels") or {}
    annotations = meta.get("annotations") or {}
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
                managed_source=labels.get(CONFIG_SOURCE_LABEL),
                exception=annotations.get(UNMANAGED_EXCEPTION_ANNOTATION),
                audit_stamped=labels.get(UNMANAGED_LABEL) == "true",
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
