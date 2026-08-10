"""Read-only Kubernetes/OpenShift REST client.

Two list calls per cluster per poll (PLAN §6), no watch. The client is deliberately thin —
raw REST over httpx rather than a generated client — because the only two resources needed
are a CRD and an OpenShift type, and both are simple to read directly.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

import httpx

from .config import VISIBILITY_TIER_TTL_DEFAULT, ClusterConfig, ConfigError

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

# The cluster's OAuth configuration — the object that holds the identity providers, and the ONLY
# place the login-gate group is written down. Three similarly named resources exist and only this one
# has identityProviders: `authentications.operator.openshift.io/cluster` carries logLevel (see
# docs/LOGIN_CAPTURE_QUICKCHECK.md) and `authentications.config.openshift.io/cluster` carries `type`.
# A single object, so this is a get rather than a list, and the grant can be narrowed with
# resourceNames — which Kubernetes honours for get, unlike list.
OAUTH_API = "/apis/config.openshift.io/v1/oauths/cluster"

# The oauth-server's own pods, and their logs. Read for ONE purpose: the lines naming who logged in,
# which exist only at `spec.logLevel: Debug` on the authentication OPERATOR CR — not the OAuth CR. See
# docs/LOGIN_CAPTURE_QUICKCHECK.md.
#
# Templated on the namespace because it is a chart value (`loginCapture.namespace`), not because it
# varies in practice: OpenShift installs the OAuth server into openshift-authentication and the grant
# the chart creates is a Role in that one namespace.
POD_API_TMPL = "/api/v1/namespaces/%s/pods"

# The namespace-configuration-operator's CRs — SAME API group as GroupSync, different
# CRDs. Cluster-scoped. These template out the RoleBindings that grant the synced groups
# their access, so they are the other half of the pipeline this dashboard watches.
NAMESPACECONFIG_API = "/apis/redhatcop.redhat.io/v1alpha1/namespaceconfigs"
GROUPCONFIG_API = "/apis/redhatcop.redhat.io/v1alpha1/groupconfigs"
ROLEBINDING_API = "/apis/rbac.authorization.k8s.io/v1/rolebindings"

# One pod-log read's wall-clock budget. The httpx timeout on _client caps the SILENCE between
# chunks, not the transfer, so a stream dripping just under it can run for minutes (measured:
# a timeout=1.0 client consumed a 3.1s dribble without raising). logincapture stamps the clock
# behind its leading-edge guard AFTER this returns, and its no-loss accounting holds only while
# that stamp lags the kubelet's window resolution by less than OVERLAP_SECONDS minus the settle
# margin — loss measured from ~58.5s of latency with the shipped constants. Twenty seconds keeps
# the overshoot far inside that, and a read this interrupts is deferred, not lost: the truncation
# path keeps the oldest lines and the watermark machinery re-reads the rest next cycle.
LOG_READ_BUDGET_SECONDS = 20.0
CLUSTERROLEBINDING_API = "/apis/rbac.authorization.k8s.io/v1/clusterrolebindings"

# ── Per-user visibility: the tier decision (docs/SPEC_per_user_visibility.md) ──────────────────

SAR_API = "/apis/authorization.k8s.io/v1/subjectaccessreviews"

# The two visibility tiers. Plain strings rather than an enum so they can sit directly in the
# `scope` field the API's responses already carry (/api/dashboard/activity's shipped contract).
TIER_SELF = "self"
TIER_ALL = "all"

# Virtual groups every real oauth token carries, ALWAYS added to the review's spec.groups.
#
# Measured with the ServiceAccount's own bearer token, 2026-08-09. The DEFAULT threshold does not
# strictly need them — `list groups` for john.doe was allowed on the strength of his admin group
# alone (spec.groups=["app-ocp-rbac-demo-cluster-admin"], reason naming CRB demo-cluster-admin-crb)
# — but the threshold is operator-CHOOSABLE, and any choice whose grant flows through
# system:authenticated fails without them: `get users/~` answered allowed=false user-only and
# allowed=true only once system:authenticated was supplied (reason: CRB basic-users of ClusterRole
# basic-user). This code cannot know which kind of threshold the operator picked, and every real
# login's token carries both, so supplying both keeps the review's input equal to the viewer's
# true token identity rather than a subset of it.
VIRTUAL_AUTH_GROUPS = ("system:authenticated", "system:authenticated:oauth")

# Re-exported from gsd.config, which is the ONE place the number is written. Kept under this
# name because the comments and docstrings in this module refer to it, and because a reader
# asking "how long is a tier cached?" looks here first.
TIER_TTL_SECONDS = float(VISIBILITY_TIER_TTL_DEFAULT)
"""How long one viewer's decided tier is believed before it is re-derived from the cluster.

THE WORST-CASE STALE-VISIBILITY WINDOW — how long a user REMOVED from an admin group can retain
the wide view — is this TTL, measured from the moment the cluster itself reflects the removal
(plus the last wide response the browser already holds, ≤30s at the UI's poll cadence). The
window equals the TTL because BOTH inputs are re-derived at every refresh: the viewer's groups
come from a fresh Group list at decision time, not the poller's snapshot — the snapshot would
add pollIntervalSeconds on top — and the SubjectAccessReview evaluates live RBAC, so revocation
by deleting a ClusterRoleBinding is caught within the same bound. What the window deliberately
does NOT cover is upstream propagation: an LDAP removal reaches the OpenShift Group object only
when the group-sync operator next syncs, on that operator's schedule, not ours.

Sixty seconds because this failure direction is OPEN — a revoked administrator keeps seeing
everything until the refresh — so the window is bought as small as the refresh cost allows:
one Group list (97ms measured at the 65-group reference scale) plus one review (25-75ms
measured) per viewer per minute, against an API server the poller already asks far more of
every cycle. It also keeps "how stale can this dashboard be" a single number: the poll
interval and this TTL are the same figure.
"""

TIER_CHECK_TIMEOUT_SECONDS = 5.0
"""The tier decision's cluster timeout, deliberately tighter than the poller's default 15s.

The decision sits on the REQUEST path — a viewer's first page load blocks on it — so this is a
user-facing bound, not a bulk-list one. Five seconds is two orders of magnitude above the
measured answer time and small enough that an API-server outage degrades to a slow dashboard
failing closed to the self view rather than a hung one. Failures are never cached (see
TierResolver.tier_for), so recovery costs nothing beyond the next request.
"""

SYSTEM_GROUP_PREFIX = "system:"
"""Kubernetes reserves this prefix for built-in identities.

Binding subjects like ``system:serviceaccounts:<ns>`` and ``system:authenticated`` are
VIRTUAL groups: they authorise real access but no Group object exists or ever will. On the
target cluster 110 of 149 distinct Group subjects are of this form, so treating "absent
from the Group API" as broken would bury the 9 genuinely broken ones in 110 false
positives. Reserved-by-convention rather than guaranteed, so these are classified and
labelled, never silently dropped."""

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


_ACCESS_GROUP_CLAUSE = re.compile(r"\(\s*(?:is)?memberof\s*=\s*([^)]+?)\s*\)", re.I)


_DN_ATTRIBUTE = re.compile(r"(?:[A-Za-z][A-Za-z0-9-]*|[0-9]+(?:\.[0-9]+)+)\Z")


def _split_unescaped(value: str, delimiter: str) -> list[str] | None:
    """Split RFC 4514 separators while preserving escaped punctuation."""
    parts, current, escaped = [], [], False
    for char in value:
        if escaped:
            current.extend(("\\", char))
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == delimiter:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    if escaped:
        return None
    parts.append("".join(current))
    return parts


def _looks_like_dn(value: str) -> bool:
    """Validate the RFC 4514 structure needed before a filter value is treated as a group DN."""
    def valid_attribute_value(raw: str) -> bool:
        if not raw:
            return False
        if raw.startswith("#"):
            encoded = raw[1:]
            return bool(encoded) and len(encoded) % 2 == 0 and bool(
                re.fullmatch(r"[0-9A-Fa-f]+", encoded))
        if raw[0] in {" ", "#"} or raw[-1] == " ":
            return False
        index = 0
        while index < len(raw):
            char = raw[index]
            if char == "\\":
                if index + 1 >= len(raw):
                    return False
                if (index + 2 < len(raw)
                        and re.fullmatch(r"[0-9A-Fa-f]{2}", raw[index + 1:index + 3])):
                    index += 3
                else:
                    index += 2
                continue
            if char in {'"', ";", "<", ">"}:
                return False
            index += 1
        return True

    rdns = _split_unescaped(value, ",")
    if not rdns or any(not rdn for rdn in rdns):
        return False
    for rdn in rdns:
        avas = _split_unescaped(rdn, "+")
        if not avas:
            return False
        for ava in avas:
            attribute, separator, attr_value = ava.partition("=")
            if (not separator or not _DN_ATTRIBUTE.fullmatch(attribute.strip())
                    or not valid_attribute_value(attr_value)):
                return False
    return True


def _access_group_from_ldap_url(url: str) -> str | None:
    """A syntactically valid gated-group DN from an RFC 2255 URL, or None."""
    _, separator, rest = url.partition("://")
    if not separator:
        return None
    parts = rest.split("?")
    if len(parts) < 4:
        return None
    filt = unquote(parts[3]).strip()
    match = _ACCESS_GROUP_CLAUSE.search(filt) if filt else None
    if not match:
        return None
    dn = match.group(1).strip()
    return dn if _looks_like_dn(dn) else None


def dn_equal(a: str | None, b: str | None) -> bool:
    """Whether two DNs name the same directory object, for our purposes.

    CASEFOLDED, because LDAP DNs are not case-sensitive in their attribute names and, for the
    directory-string syntax that cn/ou/dc use, not in their values either. The group-sync operator
    writes a group's DN into `openshift.io/ldap.uid` exactly as the directory returned it, while a DN
    typed into values.yaml or copied out of an Active Directory console is conventionally written
    `CN=...,OU=...,DC=...`. An exact comparison would then report "the gate group is not synced" on a
    cluster where it is synced perfectly well — a false negative that reads as a missing prerequisite.

    DELIBERATELY NOT a full RFC 4514 comparison: that would need to normalise escaping, optional
    spaces around the commas, and attribute aliases (`cn` vs `commonName`). Both strings here come
    from a machine — one from the operator's annotation, one from the OAuth CR's filter or a value
    the operator pasted from the same directory — so casefold plus strip covers what actually differs
    and adds no parser to get wrong. If a directory ever needs more, this is the one place to change.
    """
    if not a or not b:
        return False
    return a.strip().casefold() == b.strip().casefold()


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

    def fetch_access_group_dn(self) -> str | None:
        """The login-gate group's DN, read out of the OAuth CR, or None if there is none to read.

        WHY THE OAUTH CR AND NOT A GUESS. An LDAP identity provider's `url` is an RFC 2255 LDAP URL
        whose fourth field is the search filter, and a cluster that gates authentication on group
        membership puts that group in the filter. Measured on the reference cluster:

          ldaps://openldap-service.ldap-testing.svc.cluster.local:636/dc=ephico2real,dc=com
              ?uid?sub?(&(uid=*)(memberOf=cn=app-ssb-autobahnusers,ou=Groups,dc=ephico2real,dc=com))
                               ^^^^^^^^ ^-------------------- the group -------------------^

        BOTH SPELLINGS, because the attribute is not standardised. OpenLDAP's memberof overlay writes
        `memberOf`; 389-ds and Oracle/Sun DSEE write `isMemberOf`; and neither is defined by an RFC, so
        a filter may use either. Matching only one would silently find nothing on half of the
        directories this runs against, and "no gate configured" and "we looked for the wrong attribute"
        would be indistinguishable. Case-insensitive too — LDAP attribute names are.

        None covers three different situations on purpose, and none of them is an error:
          * FORBIDDEN — the optional grant on oauths/cluster was declined. Set the DN explicitly.
          * no LDAP identity provider at all — nothing to discover.
          * an LDAP provider whose filter carries no membership clause — there IS no gate, and every
            account in the search base can sign in. That is a finding, and the caller reports it as
            one rather than rendering an empty panel.
        """
        with self._client() as client:
            try:
                oauth = self._get(client, OAUTH_API, {})
            except ClusterError as exc:
                if exc.outcome == FORBIDDEN and OAUTH_API in exc.message:
                    log.debug("%s: not permitted to read the OAuth CR — the login-gate group "
                              "cannot be discovered; set clusterAccessGroup explicitly",
                              self.cluster.name)
                    return None
                # Anchored on the path, following fetch()'s reasoning: the message carries 200
                # characters of the response BODY, so a 500 whose body happens to mention 404 must
                # not be read as "no OAuth CR here".
                if exc.message.startswith(f"HTTP 404 on {OAUTH_API}"):
                    log.debug("%s: no OAuth CR — not an OpenShift cluster, or none configured",
                              self.cluster.name)
                    return None
                raise
        for idp in (oauth.get("spec") or {}).get("identityProviders") or []:
            url = ((idp.get("ldap") or {}).get("url") or "").strip()
            if not url:
                continue
            dn = _access_group_from_ldap_url(url)
            if dn:
                log.debug("%s: login-gate group discovered from identity provider %r: %s",
                          self.cluster.name, idp.get("name"), dn)
                return dn
        return None

    def fetch_oauth_pods(self, namespace: str) -> list[str] | None:
        """Names of the Running oauth-server pods, or None when we may not list them.

        DISCOVERY IS NOT OPTIONAL. Pod names are generated, production runs two or three replicas, and
        every roll replaces them — so there is no fixed name to read and no Deployment log subresource
        to read instead (verified: `GET .../deployments/oauth-openshift/log` returns "the server could
        not find the requested resource"). `oc logs deploy/x` only looks combined; the client resolves
        the Deployment to its pods and reads each one, which is what this does.

        Only Running pods. A Pending pod has produced nothing yet, and a Terminating one is mid-roll —
        both are read next cycle if they are still there, and neither is worth a failed request.

        None means FORBIDDEN, deliberately distinct from [] (permitted, no pods found). The grant is
        optional: an install that never enabled loginCapture, or upgraded the image without
        re-applying RBAC, gets a 403 here and must degrade rather than fail the poll.
        """
        path = POD_API_TMPL % namespace
        with self._client() as client:
            try:
                items = self._list_all(client, path)
            except ClusterError as exc:
                if exc.outcome == FORBIDDEN and path in exc.message:
                    log.info(
                        "%s: not permitted to list pods in %s — login capture is off. Grant it with "
                        "loginCapture.enabled=true.", self.cluster.name, namespace,
                    )
                    return None
                raise
        return [
            name for obj in items
            if (obj.get("status") or {}).get("phase") == "Running"
            and (name := (obj.get("metadata") or {}).get("name"))
        ]

    def fetch_pod_log(
        self,
        namespace: str,
        pod_name: str,
        since_seconds: int | None = None,
        max_bytes: int = 8 * 1024 * 1024,
    ) -> list[str] | None:
        """Timestamped log lines for one pod, or None when this pod cannot be read right now.

        NOT THROUGH `_get()`, and that is mandatory rather than stylistic: `_get` always calls
        `response.json()`, and this endpoint returns TEXT. `_client()` IS used — it only supplies the
        bearer token and CA verification, which this needs exactly as much as any other call.

        STREAMED, AND BYTE-BOUNDED — in BYTES, counted before any line is assembled. The previous
        draft counted characters of lines `iter_lines()` had already buffered whole, so a single
        line larger than the cap was held in memory before it could be measured, and a multi-byte
        log undercounted. Stopping at the cap also ends the transfer instead of paying for lines
        that would be discarded.

        A CAP HIT KEEPS THE OLDEST LINES OF THE WINDOW, deliberately. The kubelet streams oldest
        first, and oldest-first is the direction the watermark machinery REQUIRES: the cursor only
        advances through lines actually returned, so the deferred newest lines fall inside the next
        cycle's window and nothing is lost — only late. Keeping the newest instead would let the
        cursor advance past everything the cap displaced and silently drop it forever; recency is
        what the next cycle gets back anyway, completeness is not. (An earlier comment here claimed
        the newest lines were kept; it described the opposite of what the code did.) The line the
        cap cuts in half is dropped for the same reason: a truncated diagnostic can mis-parse — a
        bind error losing its `data` sub-code reads as a plain wrong password — and the whole line
        is inside the next cycle's overlap.

        BOUNDED IN WALL-CLOCK TIME as well, and on the same path as the cap. The client's timeout
        only caps the gap between chunks, so it bounds nothing about the whole transfer — and the
        capture loop derives its leading-edge guard from a clock stamped AFTER this returns, so
        every second spent here widens the band of attempts that guard throws away for good. See
        LOG_READ_BUDGET_SECONDS for the measured threshold where that band reaches rows no cycle
        ever recorded.

        `timestamps=true` is what makes the result usable at all — it prefixes each line with the
        kubelet's RFC3339 UTC stamp. klog's own stamp carries no year and no timezone.

        RETURNS None FOR THE ORDINARY ROLL, RAISES FOR THE REST, and the distinction is the point:

          404              the pod went away between listing and reading. Every roll does this.
          400 not-ready    the container has not started, so there is no log yet. Measured message:
                           "container nope is not valid for pod ..." — reason BadRequest.
          403              the grant is missing. LOGGED AT WARNING, because it is permanent and will
                           not fix itself, and a silent None here looks identical to "nobody logged
                           in" forever.
          any other        raised, so a real outage is not mistaken for roll noise.
        """
        params: dict[str, Any] = {"timestamps": "true"}
        if since_seconds is not None:
            params["sinceSeconds"] = str(since_seconds)
        path = f"{POD_API_TMPL % namespace}/{pod_name}/log"

        chunks: list[bytes] = []
        size = 0
        truncated = False
        over_budget = False
        started = time.monotonic()
        try:
            with self._client() as client:
                with client.stream("GET", path, params=params) as response:
                    if response.status_code >= 400:
                        response.read()
                        return self._log_read_refused(response, namespace, pod_name)
                    for chunk in response.iter_bytes(chunk_size=min(64 * 1024, max(1, max_bytes))):
                        if time.monotonic() - started > LOG_READ_BUDGET_SECONDS:
                            # Checked before the chunk is kept: a chunk that arrived past the budget
                            # proves the transfer is the slow kind, and keeping it would end the
                            # batch mid-line anyway — the pop below drops the tail either way.
                            truncated = over_budget = True
                            break
                        room = max_bytes - size
                        if len(chunk) >= room:
                            chunks.append(chunk[:room])
                            size = max_bytes
                            truncated = True
                            break
                        chunks.append(chunk)
                        size += len(chunk)
        except httpx.HTTPError as exc:
            # A connect error or timeout reading ONE pod must not fail the cycle: the other pods still
            # have lines, and this one is retried next time from the same watermark.
            log.info("%s: could not read %s log (%s: %s)",
                     self.cluster.name, pod_name, type(exc).__name__, exc)
            return None

        # errors="replace" cannot corrupt a kept line: the only place a multi-byte character can be
        # split is the cap boundary, and the line holding it is popped below.
        lines = b"".join(chunks).decode("utf-8", errors="replace").splitlines()
        if truncated:
            if lines:
                lines.pop()
            if over_budget:
                log.info(
                    "%s: %s log read exceeded its %.0fs budget after %d lines; the OLDEST lines of "
                    "this window are kept, and the rest fall inside the next cycle's window once "
                    "the watermark has advanced",
                    self.cluster.name, pod_name, LOG_READ_BUDGET_SECONDS, len(lines),
                )
            else:
                log.info(
                    "%s: %s log hit the %d-byte cap after %d lines; the OLDEST lines of this window "
                    "are kept, and the rest fall inside the next cycle's window once the watermark "
                    "has advanced",
                    self.cluster.name, pod_name, max_bytes, len(lines),
                )
        return lines

    def _log_read_refused(
        self, response: httpx.Response, namespace: str, pod_name: str
    ) -> list[str] | None:
        """Classify a >=400 on a pod-log read: benign roll noise, or something worth saying out loud.

        The Kubernetes Status body carries `reason` and `message`, which is the only way to tell a
        container-not-ready 400 from a 400 that means something else. Guessing from the code alone is
        what turns a permanent misconfiguration into indistinguishable debug noise.
        """
        try:
            body = response.json()
        except ValueError:
            body = {}
        reason = body.get("reason") or ""
        message = body.get("message") or response.text[:200]
        code = response.status_code

        if code == 404:
            log.debug("%s: %s is gone (read raced a roll)", self.cluster.name, pod_name)
            return None
        if code == 403:
            log.warning(
                "%s: FORBIDDEN reading %s/%s log — capture will record nothing until this is fixed. "
                "The chart grants it with loginCapture.enabled=true (a Role in %s). Reason: %s",
                self.cluster.name, namespace, pod_name, namespace, reason or code,
            )
            return None
        if code == 400 and ("ContainerCreating" in message or "not started" in message
                            or "is waiting to start" in message):
            log.debug("%s: %s container not ready yet (%s)", self.cluster.name, pod_name, reason)
            return None
        if code == 401:
            raise ClusterError(AUTH_FAILED, f"401 Unauthorized reading {pod_name} log")
        # Everything else — an unexpected 400 included — is surfaced rather than swallowed.
        log.warning("%s: unexpected HTTP %d reading %s log (reason=%s): %s",
                    self.cluster.name, code, pod_name, reason or "-", message[:200])
        return None

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

    def fetch_groups_of_user(self, user_name: str) -> list[str]:
        """Names of the OpenShift Groups this user belongs to, read FRESH from the cluster.

        Fresh rather than from the poll snapshot, deliberately: this feeds spec.groups of the
        visibility SubjectAccessReview, and a snapshot input would stretch a revoked admin's
        retained wide view from the verdict TTL to pollIntervalSeconds + the TTL — in the
        direction that fails OPEN. Read at decision time, the window is the TTL alone (see
        TIER_TTL_SECONDS). Cost measured 2026-08-09: 97ms for the 65-group reference cluster,
        paid once per viewer per TTL. Paged like every other list here, so a cluster with more
        groups than one page holds resolves complete memberships rather than a silent subset.

        MEMBERSHIP IS MATCHED BYTE-EXACT. OpenShift User names are case-sensitive — two Users
        differing only in case are two identities — so a casefolded match would hand one of
        them the other's groups, and with them possibly the other's tier.
        """
        with self._client() as client:
            items = self._list_all(client, GROUP_API)
        return sorted(
            name
            for obj in items
            if (name := (obj.get("metadata") or {}).get("name"))
            and any(str(member) == user_name for member in obj.get("users") or [])
        )

    def create_subject_access_review(
        self, user: str, groups: list[str], resource_attributes: dict[str, str]
    ) -> bool:
        """One authorization.k8s.io/v1 SubjectAccessReview, created as our own ServiceAccount.

        spec.groups IS NOT OPTIONAL. A SubjectAccessReview resolves no group membership on its
        own: asked user-only about john.doe — cluster-admin via Group
        app-ocp-rbac-demo-cluster-admin — the API server answered allowed=false, and answered
        allowed=true only once that group was supplied in spec.groups (measured twice with the
        ServiceAccount's own bearer token; reason names CRB demo-cluster-admin-crb). Every real
        administrator on the reference cluster is group-granted, so omitting the groups would
        not weaken the check — it would invert the feature.

        An authorization QUERY, not a write: it creates no persistent object, so the
        ServiceAccount's no-write-verb rule holds. The permission is the `create
        subjectaccessreviews` half of system:auth-delegator, verified sufficient at runtime —
        this exact POST answered 201 under a token minted for the ServiceAccount.

        Returns True ONLY for a well-formed boolean status.allowed=true. Everything that is not
        a clean answer — connect error, timeout, 401, 403, any other >=400, a non-JSON body, a
        missing or non-boolean allowed — raises ClusterError, which the caller collapses to the
        self tier: the absence of an answer must never read as "allowed".
        """
        body = {
            "apiVersion": "authorization.k8s.io/v1",
            "kind": "SubjectAccessReview",
            "spec": {"user": user, "groups": groups, "resourceAttributes": resource_attributes},
        }
        with self._client() as client:
            try:
                response = client.post(SAR_API, json=body)
            except httpx.HTTPError as exc:
                raise ClusterError(UNREACHABLE, f"{type(exc).__name__}: {exc}") from exc
        if response.status_code == 401:
            raise ClusterError(AUTH_FAILED, "401 Unauthorized creating a SubjectAccessReview")
        if response.status_code == 403:
            raise ClusterError(
                FORBIDDEN,
                f"403 Forbidden on {SAR_API} — the ServiceAccount lacks `create "
                f"subjectaccessreviews` (the system:auth-delegator grant)",
            )
        if response.status_code >= 400:
            raise ClusterError(
                UNREACHABLE, f"HTTP {response.status_code} on {SAR_API}: {response.text[:200]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ClusterError(UNREACHABLE, f"non-JSON response from {SAR_API}: {exc}") from exc
        allowed = (payload.get("status") or {}).get("allowed")
        if not isinstance(allowed, bool):
            raise ClusterError(
                UNREACHABLE,
                f"{SAR_API} answered without a boolean status.allowed "
                f"(kind={payload.get('kind')!r}) — refusing to treat this as a decision",
            )
        return allowed


class TierResolver:
    """Decides, per viewer, self view or all view — by asking the cluster, failing closed.

    THE DECISION. One SubjectAccessReview, created as the dashboard's own ServiceAccount,
    naming the viewer AND the viewer's OpenShift Group memberships plus the virtual groups
    every token carries (VIRTUAL_AUTH_GROUPS). allowed=true is the all tier; a clean
    allowed=false, a missing identity, and EVERY failure are the self tier. The shape of the
    review — verb, resource, apiGroup, optional namespace — is the operator's choice
    (Settings.visibility_admin_sar_*), defaulting to `list groups.user.openshift.io`, which
    admits cluster-admin and cluster-reader and nobody else among the stock roles (measured;
    `edit` and `view` pass no cluster-scoped list at all).

    WHY THE GROUPS COME FROM THE CLUSTER AND NOT FROM THE REQUEST. Nothing upstream has them:
    openshift/oauth-proxy forwards only X-Forwarded-User/-Email (its SessionState has no
    Groups field — read in source, not inferred), and SelfSubjectRulesReview answers as the
    caller, needing a token this app deliberately does not hold. The Group objects read here
    are the same objects RBAC itself evaluates, so the review's input mirrors what the
    viewer's real token would carry, staleness aside — and the staleness bound is
    TIER_TTL_SECONDS, where the worst-case window is stated.

    Thread-safe: handlers run in FastAPI's threadpool, so the cache is guarded. Concurrent
    cold-cache requests for one viewer are SINGLE-FLIGHTED: the first becomes the leader and
    resolves, the rest wait on its result. Duplicate reviews used to be tolerated ("one spare
    ~150ms round-trip") because the browser fetched its endpoints one at a time — at most two
    could race. The page now dispatches four to seven requests in one burst (index.html's
    refresh()), so an unserialised cold interval would bill the API server four to seven
    group-reads plus reviews per viewer, every TTL. Followers of a FAILED leader fail closed
    to the self view for that request, uncached — the same "a failure is not a decision"
    contract as the resolver's own error path.
    """

    def __init__(
        self,
        cluster: ClusterConfig,
        *,
        verb: str,
        resource: str,
        api_group: str = "",
        namespace: str = "",
        subresource: str,
        ttl_seconds: float,
        observe: Callable[[str], None] | None = None,
    ):
        # ttl_seconds is REQUIRED and deliberately has no default. It used to default to
        # TIER_TTL_SECONDS, and that default is precisely what hid the wiring bug: nothing
        # passed the configured value in, the constructor supplied an identical 60, and the
        # operator's knob did nothing while every default-value test agreed. A required
        # argument turns that from a silent no-op into a TypeError at construction, which is
        # the loudest place to find it. The canonical default now belongs to the caller
        # (Settings.visibility_tier_ttl_seconds), where an operator can actually change it.
        self._kube = ClusterClient(cluster, timeout=TIER_CHECK_TIMEOUT_SECONDS)
        # resourceAttributes calls the API group `group`; an empty string is the CORE group
        # (pods, namespaces), so it is passed through rather than treated as unset.
        self._attributes = {"verb": verb, "resource": resource, "group": api_group}
        if namespace:
            self._attributes["namespace"] = namespace
        # subresource is REQUIRED for the same reason ttl_seconds is, and it was the same bug:
        # Settings has parsed `resource: pods/log` into resource=pods + subresource=log since
        # the tier shipped, the chart's own guard explicitly ALLOWS that form, and this
        # constructor never accepted the second half. So an operator who narrowed the threshold
        # to `pods/log` was silently checked for `pods` — a DIFFERENT permission, potentially a
        # broader one, admitting more readers to the wide view than they asked for, with
        # nothing on screen or in the log to say so. An empty string is the ordinary value and
        # means "no subresource"; it is still passed explicitly so a caller cannot omit it and
        # reintroduce the silence.
        if subresource:
            self._attributes["subresource"] = subresource
        self._ttl = ttl_seconds
        # The metrics seam (docs/DESIGN_metrics_refresh.md §3.1): called with one enum
        # outcome per FRESH resolution. A callback and not a metrics import, so this module
        # stays cluster I/O, buildable and testable without the metrics module — the app
        # wires the two at build time.
        self._observe = observe
        self._cache: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()
        # One resolution in flight per viewer. Created under _lock by the leader, waited on
        # by followers, and always popped-and-set in the leader's finally — a leader that
        # raises must still wake its followers or they block for the full wait timeout.
        self._inflight: dict[str, threading.Event] = {}
        if not verb.strip() or not resource.strip():
            # Said once at startup rather than once per refused review. The API server will
            # reject the malformed SubjectAccessReview and every reader will fail closed to
            # the self view — safe, but it would otherwise present as "the feature broke",
            # diagnosed from one warning per request instead of one plain sentence.
            log.warning(
                "visibility admin threshold is malformed (verb=%r resource=%r) — every "
                "review it produces will be refused, so every reader gets the self view "
                "until the threshold is fixed",
                verb, resource,
            )

    def tier_for(self, viewer: str | None) -> str:
        """The tier for one viewer. Never raises; everything indeterminate is the self tier."""
        if not viewer:
            # No identity, no wide view. Whether ANY identity is trustworthy is the caller's
            # oauth-proxy guard; this is the belt to that brace.
            return TIER_SELF
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(viewer)
            if cached is not None and cached[0] > now:
                return cached[1]
            waiter = self._inflight.get(viewer)
            if waiter is None:
                self._inflight[viewer] = threading.Event()
        if waiter is not None:
            # A resolution for this viewer is already out; ride it instead of duplicating
            # it. The wait is bounded by the leader's own worst case (two cluster calls,
            # each capped at TIER_CHECK_TIMEOUT_SECONDS) plus margin — a wedged leader must
            # not wedge its followers past that.
            waiter.wait(TIER_CHECK_TIMEOUT_SECONDS * 2 + 1)
            with self._lock:
                cached = self._cache.get(viewer)
            if cached is not None and cached[0] > time.monotonic():
                return cached[1]
            # The leader failed (failures are deliberately not cached) or timed out: fail
            # closed for THIS request, cache nothing — a failure is not a decision.
            return TIER_SELF
        try:
            return self._resolve_and_cache(viewer, now)
        finally:
            # ALWAYS wake the followers — success, failure and bug alike. A leader that
            # returned without setting the event would hold every follower for the full
            # wait timeout, turning one slow review into a page-wide stall.
            with self._lock:
                event = self._inflight.pop(viewer, None)
            if event is not None:
                event.set()

    def _note(self, outcome: str) -> None:
        """Report one fresh check's outcome to the observe seam. Best-effort by contract:
        the tier is already decided by the time this runs, and a metrics bug must never
        break a security decision or un-fail-closed anything."""
        if self._observe is None:
            return
        try:
            self._observe(outcome)
        except Exception:  # noqa: BLE001
            log.exception("visibility tier metrics callback failed; the tier is unaffected")

    def _resolve_and_cache(self, viewer: str, now: float) -> str:
        """The leader's half of tier_for: one review, cached on success only."""
        try:
            groups = self._kube.fetch_groups_of_user(viewer)
            allowed = self._kube.create_subject_access_review(
                viewer, [*groups, *VIRTUAL_AUTH_GROUPS], self._attributes
            )
        except ClusterError as exc:
            # EVERY failure — unreachable, timeout, 401, 403, malformed — is the self tier,
            # and it is NOT cached: a failure is not a decision, and caching one would pin an
            # administrator to the narrow view for a full TTL over a transient blip. The
            # reader still gets a page (their own data), never an error, so this warning is
            # the only place the cause is visible.
            log.warning(
                "%s: visibility tier for %r is indeterminate (%s: %s) — failing closed to "
                "the self view for this request",
                self._kube.cluster.name, viewer, exc.outcome, exc.message,
            )
            # exc.outcome is the bounded kube vocabulary (unreachable/auth_failed/
            # forbidden), which is exactly the metric's failure enum.
            self._note(exc.outcome)
            return TIER_SELF
        except Exception:
            # A bug in this path must degrade the same way a cluster failure does: the tier
            # is a security decision, and an exception escaping into the handler would turn
            # a fail-closed control into a 500 page.
            log.exception(
                "%s: visibility tier for %r is indeterminate — failing closed to the self "
                "view for this request",
                self._kube.cluster.name, viewer,
            )
            self._note("error")
            return TIER_SELF
        tier = TIER_ALL if allowed else TIER_SELF
        self._note("allowed" if allowed else "denied")
        with self._lock:
            if len(self._cache) > 512:
                # Viewers are real authenticated people, so this stays small; the sweep only
                # exists so years of one-off names cannot grow the dict without bound.
                self._cache = {k: v for k, v in self._cache.items() if v[0] > now}
            self._cache[viewer] = (now + self._ttl, tier)
        return tier

    # `resolve` is the seam name the API publishes (app.state.tier_resolver, whose contract
    # the visibility tests substitute); `tier_for` is this class's own vocabulary. One
    # implementation under both names, so neither caller can drift from the other.
    resolve = tier_for


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
    # DISTINCT, sorted. Sorted so a membership diff between polls reflects real change rather than API
    # ordering — and distinct because the array CAN repeat a name.
    #
    # Measured, not defensive. A group carrying both membership attributes (one structural objectClass
    # plus AUXILIARY extensibleObject, which is the only schema-valid way to hold both — OpenLDAP
    # rejects groupOfNames + groupOfUniqueNames on one entry as an incompatible structural chain)
    # synced as ["john.doe","jane.smith","john.doe","bob.wilson"]. The operator's ExtractMembers
    # APPENDS the values of each configured membership attribute and does not deduplicate, and nothing
    # downstream of it does either — the Group object itself carries the repeat.
    #
    # Without this the dashboard reported `member_count: 4` above a list of THREE people, because the
    # count came from this array while the list came from group_member, whose primary key had already
    # collapsed the duplicate. One of those two numbers had to be wrong; three is the true one.
    members = sorted({str(u) for u in users})
    return GroupView(
        name=meta.get("name", ""),
        member_count=len(members),
        sync_provider=labels.get(SYNC_PROVIDER_LABEL),
        group_synced_at=annotations.get(SYNC_TIME_ANNOTATION),
        ldap_uid=annotations.get(LDAP_UID_ANNOTATION),
        members=members,
    )
