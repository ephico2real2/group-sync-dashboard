"""Read-only HTTP API (PLAN §11).

No endpoint returns a token or accepts one from the browser. The frontend talks only to this
service and never holds a cluster credential (PLAN §9).
"""

from __future__ import annotations

import functools
import logging
import hashlib
import html
from urllib.parse import quote
import os
from email.utils import formatdate, parsedate_to_datetime
import re
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from . import TITLE, __version__
from . import state as st
from .activity import EMAIL_HEADER, INTERACTION_HEADER, USER_HEADER, ActivityRecorder
from .home import HOME_CHANGES_DAYS, HOME_EVENTS_LIMIT, derive_answer, group_changes
from .config import (
    IDENTITY_NONE, IDENTITY_SAME_AS_HOST, VISIBILITY_HIDDEN, VISIBILITY_INHERIT,
    VISIBILITY_REMOTE_SAR, VISIBILITY_SELF_ONLY, Settings, load_settings,
)
from .kube import TIER_ALL, TIER_SELF, TierResolver
from .kyverno import CONTROLLED_KINDS
from .leader import LeaderElector, own_namespace
from .metrics import RuntimeSignals, build_registry
from .poller import Poller
from .reporting import REPORT_PREFIX
from .reporting.ticket import TicketError, load_secret, mint
from .storage import StorageBackend, open_backend
from . import loginlog

log = logging.getLogger(__name__)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

# The two page sources the / and /signed-out handlers render. Under the mount they are refused
# by normalised basename, case-folded: StaticFiles collapses `index.html/` and `//index.html` to
# the same file, and a case-insensitive volume opens `Index.html` as it — every one of those
# served the raw token before this (see the routes ahead of the mount in build_app).
PAGE_SOURCES = frozenset({"index.html", "signed-out.html"})


class PageSourceRefusingStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope) -> Response:
        if os.path.basename(path).lower() in PAGE_SOURCES:
            return PlainTextResponse("Not Found", status_code=404)
        return await super().get_response(path, scope)

# Mirrors oauthProxy.skipAuthRegex. Requests here reach the app WITHOUT authentication, so
# nothing they claim about identity can be believed or recorded.
# Paths that reach the app WITHOUT authentication, so nothing they claim about identity can be
# believed — and therefore nothing they claim may be recorded. /signed-out is the proxy's
# -logout-url landing page: it exists precisely for the moment the session cookie has just been
# cleared, so it is unauthenticated by design rather than by oversight.
#
# THIS SET DRIFTED FROM THE PROXY'S REGEX AND IT WAS EXPLOITABLE. `oauthProxy.skipAuthRegex` gained
# `static/(app\.css|favicon\.svg)` on 2026-08-08 (f42e60b); this set was last touched on 2026-08-02
# (98d4ec6). For six days the proxy passed those two paths through unauthenticated — where every
# header is the caller's own — while this set did not list them, so `record_dashboard_use` treated a
# caller-supplied X-Forwarded-User there as a verified identity. Measured against the live route:
#
#   curl -H 'X-Forwarded-User: PROBE-forged-unauth' -H 'X-GSD-Interaction: 1' .../static/app.css
#   -> 200, and one row ('PROBE-forged-unauth', 'PROBE@forged.invalid', '2026-08-11', 1)
#      in dashboard_user_activity, written by an unauthenticated caller.
#
# The Usage tab presents that table as a record of who accessed a governance dashboard, so anyone
# who could reach the Route could put any name on any day into it.
#
# 98d4ec6 shipped tests/test_session_api.py::test_records_no_activity_even_with_forged_headers,
# which asserts exactly this invariant — six days before the regex outgrew it. It kept passing,
# because it exercises the four paths that were in this set when it was written. A denylist of exact
# paths is only as good as somebody remembering to extend it, which is why the prefix rule below and
# tests/test_skip_auth_parity.py now exist.
SKIP_AUTH_PATHS = frozenset({"/healthz", "/readyz", "/metrics", "/signed-out"})

#: Whole subtrees where identity is never trustworthy, checked by prefix so a new file cannot open
#: the hole again. `/static/` is the whole asset tree, not only the two files the regex currently
#: exempts, and that is deliberately WIDER than the regex: a stylesheet or icon fetch is not a human
#: interaction, so declining to record one costs nothing whether it arrived authenticated or not.
#: Widening the regex to another asset therefore cannot reintroduce the defect.
UNTRUSTED_IDENTITY_PREFIXES = ("/static/",)


def identity_is_trustworthy(path: str) -> bool:
    """Did this request pass the proxy, so the identity headers on it are the proxy's own?

    The one question `record_dashboard_use` must answer before it believes a header. On a path the
    proxy skips, every header is the caller's own — there is no header the app can read to tell the
    two cases apart, because on an authenticated path the proxy OVERWRITES what the client sent and
    on a skipped path it passes it through. So the path is the only available signal, and this is
    the single place that decides it.
    """
    return path not in SKIP_AUTH_PATHS and not path.startswith(UNTRUSTED_IDENTITY_PREFIXES)


# The outcome vocabulary, read OFF THE PARSER rather than restated here. loginlog.py is where an
# outcome is decided, so a new one (a new AD sub-code, say) must not require editing a second list that
# then silently rejects it in a query parameter. Each value is escaped because this vocabulary is
# DATA inside the validator, never regex syntax; otherwise a later dot, bracket or pipe widens what
# the query accepts while the store still compares the value literally.
LOGIN_OUTCOMES = tuple(
    v for k, v in vars(loginlog).items() if k.startswith("OUTCOME_") and isinstance(v, str)
)


def _login_outcome_pattern(outcomes: tuple[str, ...]) -> str:
    """Treat parser outcomes as literal vocabulary, never as regex source text."""
    return f"^({'|'.join(re.escape(value) for value in outcomes)})$"


LOGIN_OUTCOME_PATTERN = _login_outcome_pattern(LOGIN_OUTCOMES)


# Alert kinds the SELF tier receives, WITH each kind's detail policy — ONE structure, so the
# kind list and the detail policy cannot disagree. Two structures that must agree is the shape
# that produced the SKIP_AUTH_PATHS defect above; a set derived from this mapping cannot drift
# from it. An ALLOW-list still: a kind added later is hidden from the narrow view until someone
# rules on it here, which is the fail-closed direction.
#
# Membership is the feed's own invariant, "an alert here always has a page behind it":
# every kind here is backed by a page the self tier sees — the cluster cards, and the GroupSync
# CRs and their events (served at self minus exactly ldap_filter and error_message, the spec's
# two named exceptions; see SELF_TIER_GROUPSYNC_FIELDS below). The VALUE is what the self tier
# gets as that kind's `detail`:
#   * None  — the computed detail is served unchanged. It carries nothing the kind's backing
#     page withholds from this reader (a poll failure's detail is the same message
#     /api/clusters serves to every tier as `error`).
#   * a str — the computed detail is REPLACED with that string at self. Replaced, never
#     omitted: index.html#function esc collapses a nullish detail to "", so an absent key
#     renders as an EMPTY reason column, which reads as "no reason exists" when the truth is
#     "withheld" — the fabricated-absence this repo already bans for aggregates ("null,
#     never 0"). The admin feed is never rewritten.
#
# `reconcile_error` is the one replaced kind: gsd/state.py#compute_alerts copies the CR's
# error_message straight into `detail` — the same operator diagnostic /groupsyncs withholds at
# self, and it can carry the service bind DN (measured on this repo's own fixture:
# 'LDAP bind failed for cn=svc,ou=people: invalid credentials'). The KIND stays, because the
# existence of a current reconcile failure is actionable and not withheld; only the text is.
#
# The excluded kinds are backed by pages the self tier does NOT see whole:
#   * `empty_group`, `unattributed`, `stale_group`, `group_count_cliff` and
#     `group_count_cliff_silenced` name groups from the self-scoped Groups tab (and an empty
#     group can never contain the viewer);
#   * `direct_user_binding` aggregates other people's grants from the self-scoped
#     user-bindings view;
#   * `dangling_binding` and `config_reconcile_error` are backed by /bindings/findings and
#     /operator-configs, which require_admin_tier now REFUSES at self (the spec-Q3 reversal).
#     A dangling_binding alert carries a group->role binding row and config_reconcile_error
#     carries an operator-config object plus its error message — the very rows those two
#     endpoints withhold — so leaving them here made the alert feed the alternate path around
#     the gate. Measured: with one dangling finding and one failing config, a self reader
#     whom BOTH endpoints 403'd still received BOTH alerts. Administrator-tier now; a dangling
#     binding grants nobody, so a self reader loses no signal they could act on.
SELF_ALERT_DETAILS: dict[str, str | None] = {
    # Poll failures — kind carries poll_outcome.status verbatim; backed by the cluster cards
    # and gsd_cluster_up on /metrics.
    "auth_failed": None,
    "forbidden": None,
    "unreachable": None,
    # GroupSync CR health — backed by /groupsyncs at every tier.
    "groupsync_crd_absent": None,
    "invalid_schedule": None,
    "sync_stopped": None,
    "overdue": None,
    "reconcile_error": "reconcile failed; diagnostic text is withheld in the self view",
}

# Derived, never restated: the admitted kinds ARE the keys of the detail policy.
SELF_ALERT_KINDS = frozenset(SELF_ALERT_DETAILS)


def _alerts_for_self(alerts: list[dict]) -> list[dict]:
    """Apply kind admission and detail policy together; a new kind defaults to withheld."""
    narrowed = []
    for alert in alerts:
        if alert["kind"] not in SELF_ALERT_DETAILS:
            continue
        replacement = SELF_ALERT_DETAILS[alert["kind"]]
        narrowed.append(alert if replacement is None else {**alert, "detail": replacement})
    return narrowed


#: The GroupSync fields a self-tier reader receives — every field the spec rules full-view.
#: docs/SPEC_per_user_visibility.md (Q3) rules CR health FULL at both tiers EXCEPT
#: `ldap_filter` and `error_message`, its two named exceptions: both can embed directory DNs
#: and the gate group (measured on this repo's own fixture, where error_message carries the
#: service bind DN), and a reader below the wide tier cannot read the CR with `oc` anyway
#: (measured: `oc auth can-i get groupsyncs.redhatcop.redhat.io` answers no for the narrowed
#: personas) — so this endpoint would be their only source, which is what makes serving the
#: two fields a leak by this project's own gate-what-oc-refuses rule.
#:
#: An ALLOWLIST even though only two fields are withheld, because a two-name denylist is the
#: SKIP_AUTH_PATHS shape above: a list somebody must remember to extend, gone stale once
#: already in this repo with an exploitable result. Projected this way, a NEW column on
#: gsd/store.py#Store.groupsyncs or a new key from gsd/api.py#enrich is withheld from the
#: narrow view by default until someone rules on it, and the partition test in
#: tests/test_visibility.py makes an unclassified addition a red build rather than a quiet
#: leak (denylist failure) or a quiet hole (stale-allowlist failure).
#:
#: A tuple, in the wide row's own key order — the store SELECT's columns, then the stitched
#: provider_keys, then enrich's derived keys — so a projected row diffs against a wide row as
#: pure omission, never reordering.
SELF_TIER_GROUPSYNC_FIELDS = (
    "name",
    "namespace",
    "schedule",
    "last_sync_at",
    "generation",
    "observed_at",
    "error_at",
    "error_generation",
    "group_count",
    "provider_keys",
    "state",
    "next_expected",
    "interval_seconds",
    "schedule_valid",
    "error_is_current",
)

#: The spec's two named exceptions, declared rather than implied so the partition test can
#: prove the two sets tile the wide row exactly: allowlist ∪ withheld == every key the
#: endpoint can emit, and nothing sits in both.
WITHHELD_AT_SELF_GROUPSYNC_FIELDS = frozenset({"ldap_filter", "error_message"})


def enrich(cr: dict, now: datetime, grace: timedelta) -> dict:
    """Attach the computed fields of PLAN §11 — state is derived, never stored.

    Module-level and pure (grace is an argument, not a closure) so the tier-policy
    partition test can derive the endpoint's complete key universe from the real code
    path — a store row through this function — instead of trusting a fixture payload
    to have exercised every column.
    """
    last_sync = st.parse_time(cr.get("last_sync_at"))
    schedule = cr.get("schedule")
    interval = st.schedule_interval(schedule, now) if schedule else None
    error_current = st.reconcile_error_is_current(
        st.parse_time(cr.get("error_at")), st.parse_time(cr.get("last_sync_at"))
    )
    return {
        **cr,
        "state": st.compute_state(last_sync, schedule, now, grace),
        "next_expected": (
            st.next_expected(schedule, now).strftime("%Y-%m-%dT%H:%M:%SZ")
            if schedule and st.next_expected(schedule, now)
            else None
        ),
        "interval_seconds": int(interval.total_seconds()) if interval else None,
        "schedule_valid": st.is_valid_schedule(schedule),
        # Surfaced separately from `error_message` so a UI cannot accidentally render a
        # stale failure as a live one (PLAN §2.1).
        "error_is_current": error_current,
    }


#: What a `no match` refusal actually was, once gate membership is known.
#:
#: THE ONE THING THE LOG CANNOT SAY. A refused directory login writes `no entries matching
#: (<filter>)`, and because the filter carries the login-gate group, a real person outside that group
#: and a username that does not exist produce byte-identical lines. The parser records `rejected` for
#: both and refuses to guess — correctly, because from the log alone there is nothing to choose
#: between them.
#:
#: With the gate group synced into OpenShift there IS something to choose between them, and it comes
#: from data the dashboard already holds rather than from any new directory read.
REFUSAL_NOT_GATED = "not_gated"
"""A REAL PERSON, outside the gate group. They are a member of at least one synced group — so the
directory knows them and this cluster governs them — and they are not in the gate group. The refusal
is the gate doing its job, and the finding is that they hold access they cannot use."""
REFUSAL_NO_RECORD = "no_record"
"""No record of this name anywhere: no synced group, no membership history. Consistent with a typo, a
probe, or somebody from a directory branch this cluster does not sync. NOT proof the account does not
exist — the dashboard reads OpenShift, not the directory — and the name is deliberately weaker than
"unknown account" for that reason."""
REFUSAL_MEMBERSHIP_DISAGREES = "membership_disagrees"
"""They ARE in the gate group according to the synced Group, and the directory search still found
nothing. Our membership data and the live directory disagree: most often a sync that has not caught up
with a removal, which is worth knowing because every other view on this dashboard trusts that data."""


def _refusal_reason(row: dict) -> str | None:
    """Resolve a `rejected` attempt against what we know about the account, or None.

    None whenever the question cannot be answered — no gate known, or an outcome that was never
    ambiguous in the first place. An outcome like `bad_password` already carries its own cause and must
    not acquire a second, competing one.
    """
    if row.get("outcome") != loginlog.OUTCOME_REJECTED:
        return None
    gated = row.get("in_access_group")
    if gated is None:
        return None                                  # no gate group known: nothing to resolve with
    if gated:
        return REFUSAL_MEMBERSHIP_DISAGREES
    if row.get("known_user") or row.get("has_history"):
        return REFUSAL_NOT_GATED
    return REFUSAL_NO_RECORD


def build_app(
    settings: Settings,
    run_poller: bool = True,
    tier_resolver: Callable[[str], str] | None = None,
    usage_tier_resolver: Callable[[str], str] | None = None,
    clusterconfig_view_resolver: Callable[[str], str] | None = None,
    clusterconfig_manage_resolver: Callable[[str], str] | None = None,
) -> FastAPI:
    """`tier_resolver` answers "which tier is this viewer?" — "all" or "self".

    Injected rather than constructed here so the SubjectAccessReview-backed resolver (the
    visibility module) stays independently testable and this app stays buildable without a
    cluster. None is a valid production state and it FAILS CLOSED: with restrictions on
    and no resolver, every reader gets the self view — never the wide one (decision D1).

    `usage_tier_resolver` is the SECOND, INDEPENDENT decider for the Usage tab alone
    (docs/SPEC_usage_admin_tier.md): a stricter threshold, its own instance and its own cache,
    because it asks a different question about the same person and a decided usage tier must
    never answer for the wide tier. Same fail-closed contract.
    """
    # The application asks for "the configured backend" and does not name an engine or its
    # tuning knobs. open_backend() owns that; see gsd/storage.py.
    store: StorageBackend = open_backend(settings)
    elector = LeaderElector(name=settings.leader_lease_name) if settings.leader_election else None
    # The process-event metrics seam (docs/DESIGN_metrics_refresh.md §2), one per app:
    # the resolvers, the poller, the activity recorder and the admin gate all report into
    # this instance, and the collector reads a snapshot of it at scrape time. Created here,
    # before anything that carries it.
    signals = RuntimeSignals()
    # This process's self-report (#156): its own cgroup and the filesystem under the database. The
    # sampler reads nothing until scraped or asked, and reads None on cgroup v1 — omitted, not zero.
    from .kpi.system import CgroupSampler, SystemMonitor, dashboard_data_bytes
    system_monitor = SystemMonitor(CgroupSampler(), os.path.dirname(os.path.abspath(settings.db_path)),
                                   own=("data", dashboard_data_bytes(settings.db_path, settings.backup_dir)))
    poller = Poller(store, settings, elector, signals=signals, system_monitor=system_monitor)
    # The report service (docs/specs/SPEC_C3_reporting_microservice.md). The token is read ONCE at
    # startup: the same bytes the report pod verifies with, so a ticket minted here is accepted
    # there. Missing or short when reporting is on is a startup failure — a module that is on and
    # cannot work is the state this repository refuses to run in.
    report_secret: bytes | None = None
    if settings.reporting_url:
        try:
            report_secret = load_secret(settings.reporting_token_file)
        except (OSError, TicketError) as exc:
            raise RuntimeError(f"reporting is on (reportingUrl set) but the token is unusable: {exc}") from exc
    grace = timedelta(seconds=settings.schedule_grace_seconds)

    # Both conditions, not either: the setting is the operator's choice, the proxy flag is
    # whether any identity we see is worth believing. See activity.py.
    activity = ActivityRecorder(
        store,
        enabled=settings.user_activity_enabled and settings.oauth_proxy_enabled,
        flush_interval_seconds=settings.user_activity_flush_seconds,
        retention_days=settings.user_activity_retention_days,
        signals=signals,
    )
    if settings.user_activity_enabled and not settings.oauth_proxy_enabled:
        log.info(
            "user-activity capture is configured on but the oauth proxy is not enabled; "
            "nothing will be recorded, because without the proxy there is no authentication "
            "and X-Forwarded-User would be caller-supplied"
        )

    # ── Per-user visibility: the tier decision (docs/SPEC_per_user_visibility.md) ──────────
    # Decided against the FIRST enabled cluster, deliberately: the oauth-proxy authenticates
    # viewers against the cluster this pod runs on, and that is the entry the chart writes
    # (kubernetes.default.svc with the pod's own projected ServiceAccount token). The tier it
    # yields gates everything this instance SHOWS — rows about other observed clusters
    # included — because the viewer's identity only means something here; remote clusters
    # never see this review.
    #
    # Constructed only when no `tier_resolver` was injected: an injected callable IS the
    # decision, and building a second decider beside it would leave two answers to one
    # question. The instance is published on app.state below (the seam tests substitute).
    resolver: TierResolver | None = None
    local_cluster = next((c for c in settings.clusters if c.enabled), None)
    if tier_resolver is None and settings.view_restrictions_enabled and local_cluster is not None:
        resolver = TierResolver(
            local_cluster,
            verb=settings.visibility_admin_sar_verb,
            resource=settings.visibility_admin_sar_resource,
            api_group=settings.visibility_admin_sar_api_group,
            namespace=settings.visibility_admin_sar_namespace,
            subresource=settings.visibility_admin_sar_subresource,
            ttl_seconds=float(settings.visibility_tier_ttl_seconds),
            # One enum outcome per fresh check, into the exposition — the only signal
            # that separates a broken SubjectAccessReview from a quiet healthy one.
            observe=functools.partial(signals.note_tier_check, "admin"),
        )
    # A SEPARATE instance for the Usage tab (docs/SPEC_usage_admin_tier.md), never the same one:
    # it asks a stricter question (a write verb the auditor cluster-reader fails) about the same
    # person, so sharing the wide tier's cache would let one verdict answer for the other. Same
    # 60s TTL, its own dict.
    usage_resolver: TierResolver | None = None
    if (usage_tier_resolver is None and settings.view_restrictions_enabled
            and local_cluster is not None):
        usage_resolver = TierResolver(
            local_cluster,
            verb=settings.visibility_usage_admin_sar_verb,
            resource=settings.visibility_usage_admin_sar_resource,
            api_group=settings.visibility_usage_admin_sar_api_group,
            namespace=settings.visibility_usage_admin_sar_namespace,
            subresource=settings.visibility_usage_admin_sar_subresource,
            ttl_seconds=float(settings.visibility_tier_ttl_seconds),
            # Its own threshold label, because it is its own decision — a usage-check
            # failure must not be read as the wide tier breaking, or vice versa.
            observe=functools.partial(signals.note_tier_check, "usage"),
        )
    # THE CLUSTER-CONFIGURATION TIER, two levels, each its own instance (#230; the operator's
    # ruling of 2026-09-20 — Argo CD's `clusters` resource with its get / create-update-delete
    # actions, asked natively as SubjectAccessReviews about the Secrets this surface exposes).
    # Two resolvers and not one, with separate caches and separate threshold labels, for the
    # reason SPEC_usage_admin_tier states about the wide tier: one verdict must never answer
    # another question, and `manage` must not imply `view` by construction.
    #
    # An empty namespace setting means THE POD'S OWN — where the cluster Secrets live — because
    # these questions are namespaced by nature; the wide tier's empty means cluster-scoped.
    #
    # INDEPENDENT OF THE WIDE-VIEW SWITCH, deliberately (review of #235, Grok C2). Building these
    # only when `visibility.enabled` is on — and widening when it is off, as the wide views do —
    # would mean that turning cluster-DATA restrictions off hands every proxy-admitted reader, the
    # auditor included, the fleet's wiring. The operator's ruling is not conditional. Usage already
    # made this call (usage_scope stays self when restrictions are off); this surface goes one step
    # further and still ASKS, so a cluster-admin keeps the tab either way.
    #
    # THE CONSEQUENCE, stated where it bites: with restrictions off a site may not have granted the
    # auth-delegator role, so the SubjectAccessReview fails and the surface refuses everyone until
    # that grant exists. That is the fail-closed direction for a view naming cluster credentials,
    # and the chart's README says so beside the two values.
    # The namespace the two questions are asked IN. Unknown (no ServiceAccount mount, no
    # GSD_NAMESPACE) must not silently become a CLUSTER-SCOPED `get secrets` — a different and far
    # broader question than the one the operator configured (review of #235, Codex C4). None here
    # means "cannot ask", and the gate refuses rather than asking the wrong thing.
    cc_namespace = own_namespace() or None
    clusterconfig_view_tier: TierResolver | None = None
    clusterconfig_manage_tier: TierResolver | None = None
    if clusterconfig_view_resolver is None and local_cluster is not None:
        clusterconfig_view_tier = TierResolver(
            local_cluster,
            verb=settings.visibility_clusterconfig_view_sar_verb,
            resource=settings.visibility_clusterconfig_view_sar_resource,
            api_group=settings.visibility_clusterconfig_view_sar_api_group,
            namespace=settings.visibility_clusterconfig_view_sar_namespace or cc_namespace or "",
            subresource=settings.visibility_clusterconfig_view_sar_subresource,
            ttl_seconds=float(settings.visibility_tier_ttl_seconds),
            observe=functools.partial(signals.note_tier_check, "clusterconfig_view"),
        )
    if clusterconfig_manage_resolver is None and local_cluster is not None:
        clusterconfig_manage_tier = TierResolver(
            local_cluster,
            verb=settings.visibility_clusterconfig_manage_sar_verb,
            resource=settings.visibility_clusterconfig_manage_sar_resource,
            api_group=settings.visibility_clusterconfig_manage_sar_api_group,
            namespace=settings.visibility_clusterconfig_manage_sar_namespace or cc_namespace or "",
            subresource=settings.visibility_clusterconfig_manage_sar_subresource,
            ttl_seconds=float(settings.visibility_tier_ttl_seconds),
            observe=functools.partial(signals.note_tier_check, "clusterconfig_manage"),
        )
    # ── Per-cluster authorization (docs/ACCESS_CONTROL.md §11) ──────────────────────────
    # One resolver PER remote cluster whose policy is remote-sar, constructed on THAT cluster's
    # ClusterConfig — so the review is created on the remote API with the remote token, and
    # fetch_groups_of_user reads the REMOTE's Group objects. That is the group-resolution trap
    # handled by construction rather than by feeding the store's snapshot, which would add
    # pollIntervalSeconds to the fail-open window. Same SAR shape as the host's (the operator
    # chose one threshold), same TTL, its own cache: per (viewer, cluster) by construction.
    # Reported under the "admin" threshold label: a failing remote review is the same
    # everyone-silently-narrowed signature the alert already watches for.
    remote_resolvers: dict[str, TierResolver] = {}
    if settings.view_restrictions_enabled:
        for c in settings.clusters:
            if not c.enabled or c is local_cluster:
                continue
            if settings.cluster_policy(c.name)[0] != VISIBILITY_REMOTE_SAR:
                continue
            remote_resolvers[c.name] = TierResolver(
                c,
                verb=settings.visibility_admin_sar_verb,
                resource=settings.visibility_admin_sar_resource,
                api_group=settings.visibility_admin_sar_api_group,
                namespace=settings.visibility_admin_sar_namespace,
                subresource=settings.visibility_admin_sar_subresource,
                ttl_seconds=float(settings.visibility_tier_ttl_seconds),
                observe=functools.partial(signals.note_tier_check, "admin"),
            )
    for c in settings.effective_clusters():
        policy, identity = settings.cluster_policy(c.name)
        if c is local_cluster or policy == VISIBILITY_INHERIT:
            continue
        # INFO once at startup, so "why is prod-east narrow for an administrator" is answered in
        # the pod log rather than by reading the values file.
        log.info("%s: per-cluster visibility policy %s, identity %s", c.name, policy, identity)
    if not settings.view_restrictions_enabled and any(
        settings.cluster_policy(c.name)[0] in (VISIBILITY_SELF_ONLY, VISIBILITY_REMOTE_SAR)
        for c in settings.effective_clusters()
    ):
        log.warning(
            "clusters[].visibility policies are set but view restrictions are OFF, so every "
            "reader sees every cluster in full; only `hidden` still applies"
        )
    if not settings.view_restrictions_enabled:
        # WARNING rather than INFO: this is the one switch that restores the measured exposure
        # (every authenticated reader sees the full RBAC surface and the login record), and the
        # pod log is where "why can everyone see everything" gets answered.
        log.warning(
            "view restrictions are OFF (visibilityEnabled=false / "
            "GSD_ENABLE_VIEW_RESTRICTIONS=false): every authenticated reader gets the full "
            "cluster view, as a deliberate operator choice"
        )
    elif resolver is None and tier_resolver is None:
        log.warning(
            "view restrictions are on but no enabled cluster is configured to answer the "
            "SubjectAccessReview — every reader will get the self view"
        )

    # ── Per-user visibility ─────────────────────────────────────────────────────────────
    # The scope decision is made in the handler and passed into the store as a bound SQL
    # parameter — the /api/dashboard/activity pattern, generalised. The store never sees
    # request identity; the UI only reflects the `scope` and `viewer` fields each scoped
    # response declares, because a UI-only narrowing is a leak with a cosmetic fix.
    # Endpoint rulings: docs/SPEC_per_user_visibility.md.
    #
    # Both conditions, not either — the ActivityRecorder composition above, for the same
    # reason: the setting is the operator's choice, the proxy flag is whether any identity
    # we see is worth believing. Without the proxy there are no authenticated readers to
    # tier — the app is an open port serving today's wide view to whoever reaches it, and
    # scoping by a header the caller typed would be theatre. The chart refuses to render
    # restrictions-on/proxy-off at template time; this warning covers hand-built
    # deployments that bypass it.
    restrict = settings.view_restrictions_enabled and settings.oauth_proxy_enabled
    if settings.view_restrictions_enabled and not settings.oauth_proxy_enabled:
        log.warning(
            "view restrictions are configured on but the oauth proxy is not enabled, so "
            "there is no trusted identity to scope views to and every reader sees "
            "everything — exactly today's proxy-less behaviour. Enable the oauth proxy to "
            "make the restriction real, or set GSD_ENABLE_VIEW_RESTRICTIONS=false to "
            "record that the wide view is a deliberate choice."
        )

    def trusted_viewer(request: Request) -> str | None:
        """X-Forwarded-User, believed only behind the proxy — the whoami rule.

        Separate from viewer_scope so full-view endpoints can stamp `viewer` on their
        response without consulting the tier resolver they do not need.
        """
        if not settings.oauth_proxy_enabled:
            return None
        return request.headers.get(USER_HEADER) or None

    def _decide(viewer: str | None, resolver_obj, fallback: Callable[[str], str] | None
                ) -> tuple[str | None, str]:
        """One threshold's decision for one viewer: the fail-closed core viewer_scope always had.

        `scope` is "all" only when the resolver POSITIVELY answers "all". No viewer, no
        resolver, an error, a junk answer — all "self" (requirements §5.4, decision D1).
        """
        if not viewer or (resolver_obj is None and fallback is None):
            signals.note_decision("admin", TIER_SELF)
            return viewer, TIER_SELF
        try:
            tier = (resolver_obj.resolve(viewer) if resolver_obj is not None
                    else fallback(viewer))
        except Exception:  # noqa: BLE001
            log.exception("tier resolution failed for %r; serving the self view", viewer)
            signals.note_decision("admin", TIER_SELF)
            return viewer, TIER_SELF
        scope = TIER_ALL if tier == TIER_ALL else TIER_SELF
        signals.note_decision("admin", scope)
        return viewer, scope

    def viewer_scope(request: Request, cluster_id: str | None = None) -> tuple[str | None, str]:
        """Resolve this request to (viewer, scope) — FOR ONE CLUSTER when one is named.

        `scope` is "all" only when restrictions are off, or when the deciding resolver
        POSITIVELY answers "all" for this viewer. Everything else — no viewer, no resolver
        wired, a resolver error or timeout, an unrecognised answer — lands on "self", never on
        the wide view (requirements §5.4, decision D1).

        WHICH RESOLVER DECIDES is the cluster's policy (docs/ACCESS_CONTROL.md §11):
          inherit     the host's resolver — the viewer's identity is the host's
          self-only   nobody decides; "self", and the VIEWER IS None when the cluster does not
                      treat the host's username as its own (identity: none), so a self-scoped
                      handler refuses rather than keying rows on a name nobody vouched for
          remote-sar  that cluster's own resolver, on its own API, with its own groups
          hidden      never reaches here: require_cluster answers 404 first
        With no cluster named — /api/whoami's headline, the Usage tab — the host decides.
        Restrictions off means off for every policy but `hidden`, which is a serving rule.
        """
        viewer = trusted_viewer(request)
        if not restrict:
            return viewer, TIER_ALL
        # "The host decides" means the host's DECIDED tier, and the host's own policy is part of
        # that decision: with no cluster named the question is the host's, and an `inherit`
        # remote under a `self-only` host is self — the host resolver alone would have widened
        # a remote the host itself refuses to widen (review of D2, Cursor).
        host = settings.host_cluster()
        if cluster_id is None:
            if host is None:
                # No enabled entry: there is no decided host tier to inherit. Fail closed
                # rather than answer `inherit` from the resolver of a cluster that is not
                # hosting anyone (review of D2, second pass, Cursor).
                signals.note_decision("admin", TIER_SELF)
                return viewer, TIER_SELF
            cluster_id = host.name
        policy, identity = settings.cluster_policy(cluster_id)
        # `inherit` follows the host's decided POLICY; the remote's identity is consulted only
        # under its own `self-only` — under inherit a self reader is keyed by the host's
        # username, as before 0.19.0 (docs/ACCESS_CONTROL.md §11). The first-pass remap applied
        # the remote's default `identity: none` after the remap and refused what §11 promised
        # (review of D2, second pass, Cursor).
        own_policy = policy
        if policy == VISIBILITY_INHERIT and host is not None and cluster_id != host.name:
            policy = settings.cluster_policy(host.name)[0]
        if policy == VISIBILITY_SELF_ONLY:
            signals.note_decision("admin", TIER_SELF)
            keep = own_policy == VISIBILITY_INHERIT or identity == IDENTITY_SAME_AS_HOST
            return (viewer if keep else None), TIER_SELF
        if policy == VISIBILITY_REMOTE_SAR:
            # Read off app.state PER REQUEST, the published seam, so a test can substitute one
            # remote's decision without a cluster. No build-time fallback: a remote cluster
            # with no resolver is a remote cluster nobody may see wide.
            remotes = getattr(app.state, "remote_tier_resolvers", None) or {}
            return _decide(viewer, remotes.get(cluster_id), None)
        state_resolver = getattr(app.state, "tier_resolver", None)
        return _decide(viewer, state_resolver, tier_resolver)

    def usage_scope(request: Request) -> tuple[str | None, str]:
        """Resolve this request to (viewer, scope) for the USAGE tab specifically.

        A SECOND, STRICTER threshold than viewer_scope, and INDEPENDENT of it
        (docs/SPEC_usage_admin_tier.md). The Usage tab is the one dataset that lives only in the
        dashboard's own database and cannot be reproduced with `oc`, so it must not fall to the
        wide tier that cluster-reader — the deliberate auditor persona — also passes. Precedence:

          1. userActivity.visibility == "all" -> every admitted reader sees all rows. The
             existing blunt escape hatch, kept unchanged.
          2. otherwise the USAGE resolver decides: its exact "all" widens; everything else — no
             resolver, an error, a junk string, no identity — is the reader's own rows.

        Fail closed like viewer_scope: only the exact string "all" ever widens. Reads the usage
        resolver off its OWN app.state seam, never the wide tier's.
        """
        viewer = trusted_viewer(request)
        # Precedence 1: the blunt operator override, independent of any tier. Preserved verbatim
        # from the pre-tier behaviour so a deployment that set it keeps working.
        # LITERAL "all": this is the chart/config vocabulary (userActivity.visibility, parsed
        # by _visibility_setting), not TierResolver's return. Do not substitute TIER_ALL here —
        # the two vocabularies have different owners and are free to diverge.
        if settings.user_activity_visibility == "all":
            # A served wide decision, counted as one: a deployment that set the blunt
            # override should see that fact on the graph rather than a mysterious all-tier.
            signals.note_decision("usage", TIER_ALL)
            return viewer, TIER_ALL
        # Restrictions off (or proxy off) runs no tier machinery — but Usage is NOT the wide
        # view, so it stays self here rather than widening. This mirrors the pre-tier behaviour,
        # where /api/dashboard/activity was governed by userActivity.visibility alone and never
        # by the visibility tier: turning cluster-data restrictions off must not, as a side
        # effect, expose colleagues' presence records.
        if not restrict:
            return viewer, TIER_SELF
        state_resolver = getattr(app.state, "usage_tier_resolver", None)
        if not viewer or (state_resolver is None and usage_tier_resolver is None):
            signals.note_decision("usage", TIER_SELF)
            return viewer, TIER_SELF
        try:
            tier = (state_resolver.resolve(viewer) if state_resolver is not None
                    else usage_tier_resolver(viewer))
        except Exception:  # noqa: BLE001
            # An API-server blip degrades the Usage VIEW to the reader's own rows, never the
            # availability and never the wide set — the same discipline viewer_scope follows.
            log.exception("usage tier resolution failed for %r; serving the self view", viewer)
            signals.note_decision("usage", TIER_SELF)
            return viewer, TIER_SELF
        scope = TIER_ALL if tier == TIER_ALL else TIER_SELF
        signals.note_decision("usage", scope)
        return viewer, scope

    def require_viewer(viewer: str | None, cluster_id: str | None = None) -> str:
        """Self-scoped data needs a name to scope to; without one it is refused.

        The /api/dashboard/activity rule: when no proxy fronts the app (or the proxy sent
        no identity header), X-Forwarded-User is whatever the caller typed, and honouring
        it would let anyone read anyone by asserting a name.

        A SECOND reason for no name, when a cluster is named: that cluster's identity policy is
        `none`, so viewer_scope withheld the host's username on purpose (docs/ACCESS_CONTROL.md
        §11). Said in its own words, and — like every refusal here — without naming the value
        that would change it: this sentence reaches the person being refused.
        """
        if not viewer:
            if (cluster_id is not None and restrict
                    and settings.cluster_policy(cluster_id)[1] == IDENTITY_NONE):
                raise HTTPException(
                    status_code=403,
                    detail="this data is scoped to a viewer, and this cluster does not treat "
                           "your identity as one of its own; only cluster-level health is "
                           "shown for it",
                )
            raise HTTPException(
                status_code=403,
                detail="this data is scoped to the authenticated viewer, and there is no "
                       "authenticated identity to scope it to",
            )
        return viewer

    def _clusterconfig_tier(request: Request, level: str) -> str:
        """One level of the cluster-configuration tier, resolved and counted. Returns TIER_ALL or
        TIER_SELF; never raises. FAIL CLOSED, which here means TIER_SELF — Argo's
        `policy.default: deny` in our vocabulary: no identity, no resolver, or an API-server blip
        all refuse. A blip must not widen a surface that names cluster credentials.

        NO `restrict` SHORT-CIRCUIT (review of #235, Grok C2): the wide views widen when
        `visibility.enabled` is off, and copying that here would re-admit the very persona this
        tier exists to exclude. Without the proxy there is no trustworthy identity either, and
        `trusted_viewer` returns None — which refuses, for the same reason.

        AND NO COMPOSITION WITH ANOTHER TIER (the operator's ruling of 2026-09-20, which reversed an
        earlier ordering): each level asks ITS OWN question and nothing else. RBAC is additive, so
        holding the auditor role AND a namespace-admin grant is not a contradiction to resolve; the
        SAR asks the action's own question, so whoever passes it can already read or create that
        Secret with `oc` — refusing them here protects nothing, and because the question IS the
        action, the ServiceAccount that performs the write is not a confused deputy. The auditor is
        excluded by the plain question, measured: the pure auditor persona answers `no` to both."""
        injected = (clusterconfig_view_resolver if level == "view" else clusterconfig_manage_resolver)
        built = (clusterconfig_view_tier if level == "view" else clusterconfig_manage_tier)
        state = getattr(app.state, f"clusterconfig_{level}_resolver", None)
        label = f"clusterconfig_{level}"
        viewer = trusted_viewer(request)
        resolver = state if state is not None else (built if built is not None else injected)
        # A question with no namespace is not this tier's question (Codex C4): refuse rather than
        # widen it to the cluster. A substituted resolver (the test seam) carries its own scope.
        if state is None and not (settings.visibility_clusterconfig_view_sar_namespace
                                  or settings.visibility_clusterconfig_manage_sar_namespace
                                  or cc_namespace):
            log.warning("cluster-configuration tier: this pod's namespace is unknown and no "
                        "visibility.clusterConfig*Sar.namespace is set, so the check cannot be "
                        "asked in a namespace; refusing %s", level)
            signals.note_decision(label, TIER_SELF)
            return TIER_SELF
        if not viewer or resolver is None:
            signals.note_decision(label, TIER_SELF)
            return TIER_SELF
        try:
            tier = resolver.resolve(viewer) if hasattr(resolver, "resolve") else resolver(viewer)
        except Exception:  # noqa: BLE001
            log.exception("cluster-configuration %s tier resolution failed for %r; refusing", level, viewer)
            signals.note_decision(label, TIER_SELF)
            return TIER_SELF
        scope = TIER_ALL if tier == TIER_ALL else TIER_SELF
        signals.note_decision(label, scope)
        return scope

    def require_clusterconfig_view(request: Request) -> str:
        """`clusterconfig:view` — Argo's `clusters, get`, asked as `get secrets` in this pod's
        namespace (Settings carries the measurement). Gates the read route, and in #230 S2 the
        tab's very existence: a reader who fails it is not shown that the surface is there.

        NOT the wide tier, deliberately. `require_admin_tier` admits cluster-reader — the auditor
        persona — by design (see usage_scope), and this surface says which clusters this instance
        reads, from which Secret, under which credential kind and trust mode. The operator's
        ruling of 2026-09-20: the auditor may neither view nor change it."""
        if _clusterconfig_tier(request, "view") != TIER_ALL:
            signals.note_admin_refusal()
            raise HTTPException(
                status_code=403,
                detail="For cluster-configuration administrators only. This view reports how this "
                       "instance is wired to its clusters — which Secret configures each one, the "
                       "kind of credential it holds and how its certificate is trusted.",
            )
        return TIER_ALL

    def require_clusterconfig_manage(request: Request) -> str:
        """`clusterconfig:manage` — Argo's `clusters, create/update/delete`, asked as `create
        secrets` in this pod's namespace. Gates the write routes (#230 S2).

        ASKED SEPARATELY, never inferred from view: a site may grant the two apart, so a reader
        who may see the wiring is not thereby allowed to change it."""
        if _clusterconfig_tier(request, "manage") != TIER_ALL:
            signals.note_admin_refusal()
            raise HTTPException(
                status_code=403,
                detail="Changing cluster configuration is reserved to cluster-configuration "
                       "administrators. This view remains readable.",
            )
        return TIER_ALL

    def require_admin_tier(request: Request, cluster_id: str | None = None) -> str:
        """The administrator tier, or a refusal that names itself as one.

        For the views that are ABOUT THE CLUSTER rather than about the reader: its whole RBAC
        binding surface and the operator's configuration (the sync CRs themselves are served at
        both tiers, projected at self — see list_groupsyncs). These cannot be scoped
        the way a membership list can — a CLUSTER-WIDE binding list names whoever it names, so
        the honest choice is the whole thing or none of it, and none of it is what a
        non-administrator gets.

        WHAT THIS DOES NOT WITHHOLD, stated because the sentence above used to imply it did.
        A non-administrator still sees the bindings on their OWN access path: `/groups/{name}`
        and `/users/{name}` embed `bindings` for a group the reader belongs to, so a reader in
        a group that holds cluster-admin can read that fact and the binding's name. That is
        deliberate — the narrowed tier exists to answer "what access do I have, and how did I
        get it", which is unanswerable without naming the binding that granted it — and it is
        bounded by membership, not by this gate: `/groups/{name}` refuses a non-member and
        `/users/{name}` refuses anyone but the reader, both BEFORE any existence lookup, so
        neither can be used to enumerate.

        The distinction is scope, not category: this gate withholds the cluster's binding
        surface, and never a reader's own. `docs/ACCESS_CONTROL.md` tabulates both. Since
        0.10.0 the Access granted tab renders exactly that at the narrowed tier — the reader's
        own `/users/{name}` bindings, with the group named — where the refusal card used to be;
        the refusal this raises is unchanged, and still what a plain reader gets from the
        endpoint itself.

        WHY A REFUSAL AND NOT A FILTER, measured on the reference cluster. An ordinary reader
        (`lateef.o`) holds none of `list clusterrolebindings`, `list rolebindings` or `list
        groups` — `oc auth can-i` answers no to all three — and /bindings/findings handed him
        236 rows anyway, 21 of them naming an admin role, including which group holds
        cluster-admin. That is a target list obtainable through the dashboard and not with
        `oc`: a privilege escalation.

        The chart already records this exact finding for the BEARER-token path, where gating
        /api on `list groups` was called "WRONG — a privilege escalation, proven on the
        reference cluster" and the floor was raised to cluster-wide RBAC read. That floor was
        never applied to the browser path, because -openshift-delegate-urls governs bearer
        tokens only and cookie sessions bypass it entirely. This is the same floor, applied
        where it was missing.

        AND IT ONLY BECAME TRUE WHEN THE DEFAULT WAS RAISED. This paragraph claimed parity while
        `visibility.adminSar` still defaulted to `list groups.user.openshift.io` — the very check
        the sentence above calls wrong. Caught by review, not by a test, because on stock roles the
        two thresholds admit the same personas and nothing observable differed. The threshold is
        the operator's to choose, so what this function guarantees is the REVIEW, not a particular
        resource; `config.py#Settings` carries the default and the measurement behind it.
        """
        _, scope = viewer_scope(request, cluster_id)
        if scope != "all":
            # Counted before the raise: a refusal that leaves no trace anywhere is how a
            # gate that broke for everyone stays indistinguishable from one nobody hit.
            signals.note_admin_refusal()
            # THE SAME SENTENCE THE CARD DRAWS, AND FIRST. The page and the API are two
            # renderings of one refusal and they used to word it differently — the card said
            # "For administrators only." while this said "reserved to the administrator tier",
            # so a caller comparing them could not tell they were the same control. The
            # operator asked for that exact phrase.
            #
            # It leads rather than trails: a client that shows only the head of a `detail`
            # would drop a trailing clause, which is the one clause that must arrive.
            #
            # Says what the view contains and that it is reserved; never the role, grant, chart
            # value or route that would widen it. This string reaches the person being refused.
            raise HTTPException(
                status_code=403,
                detail="For administrators only. This view reports the cluster's own RBAC "
                       "binding surface and operator configuration rather than anything "
                       "belonging to the reader.",
            )
        return scope

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if run_poller:
            if elector is not None:
                elector.start()
            poller.start()
        else:
            # Still register configured clusters so the overview lists them as
            # never-polled rather than omitting them entirely.
            for cluster in settings.effective_clusters():
                store.upsert_cluster(cluster.name, cluster.api_url, cluster.enabled,
                                     source=cluster.source, credential=cluster.credential_kind)
        activity.start()
        yield
        # Before the store closes: stop() does a final flush, and the buffer is only in
        # memory. Every replica runs this, leader or not — each serves its own requests.
        activity.stop()
        poller.stop()
        if elector is not None:
            elector.stop()
        store.close()

    # Docs live under /api, not at FastAPI's default /docs, for one reason that matters:
    # oauthProxy.skipAuthRegex admits ^/(healthz|readyz|metrics)$ and nothing else, so every
    # /api path is authenticated by the proxy exactly like the data it describes. A schema
    # naming every endpoint and every field is a map of this cluster's RBAC surface; it
    # belongs behind the same door as the data.
    #
    #   /api            the schema browser (Swagger UI)
    #   /api/docs       the same, for anyone who types the conventional path
    #   /api/redoc      the reference rendering
    #   /api/openapi.json  the spec itself, for codegen and for the drift test
    app = FastAPI(
        title=TITLE,
        version=__version__,
        lifespan=lifespan,
        # The built-in routes are disabled and re-served below from vendored assets:
        # FastAPI's defaults load Swagger UI and ReDoc from cdn.jsdelivr.net, which renders
        # a blank page on a cluster with no route to the internet — the kind this chart is
        # written for.
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
        description=(
            "Read-only observability for the OpenShift group-sync-operator.\n\n"
            "Every endpoint is a GET and nothing here returns or accepts a cluster "
            "credential. Timestamps are UTC and end in `Z`; list endpoints that can grow "
            "without bound report `total` alongside their page so a truncated response "
            "cannot be mistaken for a complete one."
        ),
    )

    @app.middleware("http")
    async def record_dashboard_use(request, call_next):
        """Note who made this request, before serving it.

        Only requests the client marked as a human action are counted. The page polls
        itself every 30s and each poll is several API calls, so counting requests measured
        how long a tab had been open rather than whether anyone used the dashboard — one
        real session read 722. See activity.INTERACTION_HEADER.

        Unauthenticated paths are excluded EXPLICITLY rather than by assuming they arrive
        header-less: they bypass the proxy (oauthProxy.skipAuthRegex), so whether they carry an
        identity header is decided by the caller — which is exactly the input that must not decide
        whether we record. See `identity_is_trustworthy`, and the exploit that proved the point.
        """
        if identity_is_trustworthy(request.url.path) and request.headers.get(INTERACTION_HEADER):
            try:
                activity.record(
                    request.headers.get(USER_HEADER), request.headers.get(EMAIL_HEADER)
                )
            except Exception:  # noqa: BLE001
                # Logged with a trace rather than swallowed, but never propagated: failing
                # to note who read a page is not a reason to fail the page.
                log.exception("could not record dashboard use; serving the request anyway")
        return await call_next(request)

    def consistent(fn):
        """Serve this handler from ONE database snapshot.

        For handlers that call the store more than once. Six independent statements are
        six independent points in time, and a poll committing between any two of them
        produces a response that is internally contradictory — a CR listing providers
        whose groups the same response says do not exist. Measured at 3.00% of reads even
        after the poll itself became atomic.

        Deliberately NOT applied to single-call handlers: a snapshot holds a WAL read-mark
        and blocks checkpointing, so it is worth taking only where it buys consistency.

        The wrapped function must be synchronous and must not stream, yield or await —
        that would hold the snapshot for the life of the response rather than the life of
        the query. tests/test_read_snapshot_scope.py enforces it.
        """
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            with store.read_snapshot():
                return fn(*args, **kwargs)
        return wrapper

    def is_served(cluster_id: str) -> bool:
        """Whether this instance serves the cluster at all — configured, enabled, and not `hidden`.

        `require_cluster`'s rule as a predicate, for the handlers that WALK the stored clusters
        instead of being handed one. Home's cross-cluster line was written against
        `store.clusters()` (polled, still enabled=1) and so named a hidden cluster the very next
        request 404s, counted its memberships and folded its history into "what changed" — the
        rule has four copies in this file and the fifth site forgot a limb (review of #158, Grok).
        """
        cluster = settings.cluster(cluster_id)
        return (cluster is not None and cluster.enabled
                and settings.cluster_policy(cluster_id)[0] != VISIBILITY_HIDDEN)

    def vouches_for_host_identity(cluster_id: str) -> bool:
        """Whether this cluster treats the host's authenticated username as one of its own.

        The name half of `viewer_scope`'s decision, answered from CONFIG alone. viewer_scope
        answers it too, but on the way it may consult a tier resolver — a `remote-sar` cluster's
        is an HTTP SubjectAccessReview — and a handler holding a read snapshot must not make one
        of those per cluster in the fleet (review of #158, Grok). Kept in step with viewer_scope's
        `keep`: restrictions off vouches for everyone; the host vouches for its own reader; an
        `inherit` remote is keyed by the host's username; `self-only` needs `identity:
        same-as-host`, which `remote-sar` is required by config validation to carry.
        """
        if not restrict:
            return True
        host = settings.host_cluster()
        if host is not None and cluster_id == host.name:
            return True
        policy, identity = settings.cluster_policy(cluster_id)
        return policy == VISIBILITY_INHERIT or identity == IDENTITY_SAME_AS_HOST

    def require_cluster(cluster_id: str):
        """The cluster, or a 404 — the SAME 404 for an id that does not exist, one whose policy is
        `hidden`, and one that is disabled/retired (removed from config), so the response is not an
        oracle over which clusters this instance watches. A retired cluster keeps its history but is
        not served (#96); hidden and disabled apply whatever the tier: they are serving rules."""
        cluster = settings.cluster(cluster_id)
        if not is_served(cluster_id):
            raise HTTPException(status_code=404, detail=f"unknown cluster {cluster_id!r}")
        return cluster

    def history_retention(table: str, since: dict[str, str | None]) -> dict:
        """The retention edge of one history table, for the wire.

        `window_days` is the configured window (0 = kept forever); `retained_since` is the
        oldest row still held for this cluster, or null. Together they let a page say
        "history retained since T" where a timeline begins at the cut — without them an
        empty or short list reads as "nothing happened", which is the false absence this
        dashboard exists to avoid. Callers pass `store.history_retained_since(cluster_id)`
        themselves, at the call site, so the API contract's store-call count (R5) sees the
        second read and holds them to @consistent — a helper that read the store would hide it.
        """
        days = {
            "membership_event": settings.membership_events_retention_days,
            "sync_event": settings.sync_events_retention_days,
            # Shares membership_event's window by design (DESIGN_binding_events.md).
            "binding_event": settings.membership_events_retention_days,
        }[table]
        return {"window_days": max(0, int(days)), "retained_since": since.get(table)}

    def _config_summary(cluster_id: str) -> dict | None:
        oc = store.operator_configs(cluster_id)
        if not oc["present"]:
            return None
        failing = sum(
            1 for c in oc["configs"]
            if c["error_at"] and (not c["success_at"] or c["error_at"] > c["success_at"])
        )
        return {"total": len(oc["configs"]), "failing": failing}

    def _binding_counts(cluster_id: str) -> dict:
        # A scalar GROUP BY, not every row materialised and counted in Python: this runs on every
        # /api/clusters, which every tab reads, and the row form grew with the cluster (measured
        # at 2,280 rows at ten times the reference cluster). Same classification, same numbers.
        # GROUP BY yields only the tiers present, so a cluster with no dangling bindings has no
        # "dangling" key — index with a default, as the pre-seeded dict this replaced did.
        counts = store.count_bindings_by_finding(cluster_id)
        return {
            "dangling_bindings": counts.get("dangling", 0),
            "unresolved_bindings": counts.get("unresolved", 0),
            "builtin_bindings": counts.get("built_in", 0),
        }

    @app.get("/api/clusterconfigs")
    @consistent
    def list_cluster_configs(request: Request) -> dict:
        """Every cluster this instance knows with WHERE it came from (SPEC_S1 C5): the values list, a
        labelled Secret (`secret:<name>`), the host; the credential's KIND and never its value; the
        Secret's other labels; the D2 options; the poll outcome the cluster table holds; and the
        current discovery cycle's findings. Administrator tier: the sources and the findings describe
        how the fleet is wired, which is not a self reader's business. The Cluster Configurations
        tab (#230 S2) is built on this payload; the writes are S2's too.

        `clusterconfig:view`, NOT the wide tier: the wide one admits the auditor persona by design
        and the operator's ruling of 2026-09-20 forbids it here. See require_clusterconfig_view."""
        require_clusterconfig_view(request)
        from .clusterconfig import LABEL_SELECTOR
        registry = settings.cluster_registry
        host = settings.host_cluster()
        polled = {row["id"]: row for row in store.clusters()}
        clusters = []
        for c in settings.effective_clusters():
            row = polled.get(c.name) or {}
            visibility, identity = settings.cluster_policy(c.name)
            clusters.append({
                "id": c.name, "source": c.source, "host": host is not None and c.name == host.name,
                "api_url": c.api_url, "enabled": c.enabled, "credential": c.credential_kind,
                "labels": dict(c.labels), "visibility": visibility, "identity": identity, "tls": c.tls_mode,
                "status": row.get("status"), "last_poll": row.get("last_poll"), "error": row.get("message"),
                "retired": False,
            })
        # A cluster the store still holds but no source names any more — a Secret that vanished, a values
        # entry removed — is retired (enabled=0, history kept, #96). The tab shows it as such rather than
        # letting it disappear: its rows are still there, and the reader should know why.
        named = {c["id"] for c in clusters}
        for row in polled.values():
            if row["id"] in named:
                continue
            clusters.append({
                "id": row["id"], "source": row["source"], "host": False, "api_url": row["api_url"],
                "enabled": False, "credential": row["credential"], "labels": {},
                "visibility": None, "identity": None, "tls": None,
                "status": row.get("status"), "last_poll": row.get("last_poll"), "error": row.get("message"),
                "retired": True,
            })
        return {
            "viewer": trusted_viewer(request), "scope": "all",
            "secrets": {"enabled": settings.cluster_secrets_enabled, "namespace": registry.namespace,
                        "label": LABEL_SELECTOR, "last_discovery": registry.last_discovery, "error": registry.error},
            "clusters": clusters,
            "findings": [f.public() for f in registry.findings()],
        }

    @app.get("/api/clusters")
    @consistent
    def list_clusters(request: Request) -> list[dict]:
        """Every observed cluster with its poll status and headline counts.

        The overview reads this. An unreachable cluster still appears, carrying its error —
        a cluster this dashboard cannot poll is a thing it exists to report, not a reason to
        omit the row.

        REACHABLE AT EVERY TIER, deliberately: the cluster selector reads this on every tab,
        and reachable/status/error is how an ordinary reader tells a broken dashboard from an
        empty one. Almost every count here is already world-readable on the unauthenticated
        /metrics (gsd_groups_total, gsd_bindings_total{finding=...}), so withholding those
        behind login would be theatre. The ONE exception is `operator_configs` below: it has
        no /metrics analogue (there is no gsd_operator_configs_total; only the failing count
        is inferable from gsd_alerts_total{kind="config_reconcile_error"}), so it is a
        genuinely private aggregate that would otherwise reach a self reader through the one
        endpoint that cannot be refused. It is withheld at self — the withheld-aggregate
        pattern /logins and /cluster-access already use — while everything with a public
        analogue stays full.
        """
        out = []
        for row in store.clusters():
            # A retired cluster (removed from config, marked enabled=0 at poll start) or one disabled
            # in config is not served: its history is kept but it leaves the selector, so it never
            # shows as `ok` with frozen data or stale alerts (#96).
            #
            # THE PREDICATE, not two of its three limbs (review of #235, OB3 C6). A Secret-sourced
            # cluster can now leave the CONFIGURATION while its row still says enabled=1 — the
            # discovery replaces the registry first and retires the row second, and on a non-leader
            # replica the row is not rewritten until the leader's own cycle. In that window
            # `settings.cluster(id)` is None, and `cluster_policy`'s defensive default for an
            # unknown id is the WIDEST one, so a cluster its Secret made `self-only` was served to a
            # wide-tier reader as `inherit`/`all`. `is_served` owns the whole rule and its docstring
            # predicted this: "the rule has four copies in this file and the fifth site forgot a
            # limb". The other three sites already walk rows through it.
            if not is_served(row["id"]):
                continue
            policy, _ = settings.cluster_policy(row["id"])
            # Decided PER CLUSTER (docs/ACCESS_CONTROL.md §11): a host administrator is not an
            # administrator of a self-only remote, and the card must not say otherwise.
            _, scope = viewer_scope(request, row["id"])
            counts = store.group_counts(row["id"])
            crs = store.groupsyncs(row["id"])
            out.append(
                {
                    "id": row["id"],
                    "api_url": row["api_url"],
                    "enabled": bool(row["enabled"]),
                    # `reachable` is explicitly None when never polled, so the UI can say
                    # "no data yet" instead of showing a healthy-looking false.
                    "reachable": None if row["status"] is None else row["status"] == "ok",
                    "status": row["status"],
                    "last_poll": row["last_poll"],
                    "error": row["message"],
                    "groupsync_count": len(crs),
                    # Disambiguates the count above: 0 CRs with the operator installed is a
                    # configuration to fix, 0 with no CRD is a different cluster shape. None
                    # when never polled. Same three-valued contract as `reachable`.
                    "groupsync_operator_present": store.groupsync_present(row["id"]),
                    "group_count": counts["total"],
                    "empty_groups": counts["empty"],
                    "unattributed_groups": counts["unattributed"],
                    "oldest_last_sync": store.oldest_last_sync(row["id"]),
                    # Compact policy-operator summary for the card. None when the CRDs are
                    # absent, so the UI can render nothing rather than a healthy-looking 0 —
                    # AND None at the self tier, where it is withheld (see the docstring): it
                    # is the one card figure with no /metrics analogue. Both cases render as
                    # nothing on the card, which is the right outcome for each.
                    "operator_configs": (
                        _config_summary(row["id"]) if scope == "all" else None),
                    # The policy this instance applies to the cluster and what it decided for
                    # THIS reader, so the selector can label a cluster it narrows. The UI
                    # renders these; it never derives them (docs/ACCESS_CONTROL.md §7).
                    "visibility": {"policy": policy, "scope": scope},
                    # Surfaced on the landing page so binding problems are discoverable
                    # without knowing to navigate anywhere. `unresolved` does not alert
                    # (it cannot be told from a not-yet-synced group), so without a count
                    # here a UI-only reader would see "No alerts" and conclude nothing is
                    # wrong while bindings grant nobody.
                    **_binding_counts(row["id"]),
                }
            )
        return out

    @app.get("/api/clusters/{cluster_id}/groupsyncs")
    def list_groupsyncs(request: Request, cluster_id: str) -> list[dict]:
        """GroupSync CRs on one cluster, with their derived state.

        `state`, `next_expected` and `error_is_current` are computed per request from the
        schedule and the last sync, never stored — a stored state would be wrong the moment
        the clock moved past it.

        SERVED AT BOTH TIERS, PROJECTED AT SELF — spec Q3's ruling, both halves. Q3
        originally served CR health, operator configuration AND the binding findings whole at
        both tiers as "governance data about objects"; 03ad446 reversed that for the RBAC
        binding surface (/bindings/findings) and the operator's private configuration
        (/operator-configs), which are the administrator tier now. THIS endpoint stays served
        on a measurement the other two do not share: /metrics is in the chart's skipAuthRegex
        and serves, to a credential-less curl, gsd_groupsync_state,
        gsd_groupsync_last_sync_timestamp_seconds and gsd_groupsync_groups_total per CR, so
        REFUSING CR health here would be theatre while that holds — and it would cost the
        Groups tab its per-provider colour slots (crSlot reads data.groupsyncs) for nothing.
        Gate /metrics first if this should ever change.

        Served is not identical, though: the SAME spec ruling names two exceptions,
        `ldap_filter` and `error_message`, omitted at the self tier because both can embed
        directory DNs and the gate group, which a narrowed reader cannot read with `oc`
        (see SELF_TIER_GROUPSYNC_FIELDS). "The Overview tab is admin-only" never protected
        them: index.html#async function refresh fetches this endpoint inside `if
        (view.cluster)`, true on EVERY page, so a narrowed reader's browser downloads the
        payload every refresh regardless of which tab they are on — not shown, but
        delivered. The wide tier receives each enriched row unchanged; the operator's
        diagnostic stays byte-for-byte.

        Still a bare list, deliberately: this endpoint is FIELD-WITHHOLDING, the
        /api/clusters class (operator_configs withheld at self on a bare list), not
        row-scoping like /groups — an envelope here would create the inconsistency it
        claimed to remove, and would break index.html#function groupsyncTable, which reads
        `.length` off the value and would paint "None observed on this cluster yet." on a
        truthy object whose `.length` is undefined, while CRs exist.
        """
        require_cluster(cluster_id)
        _, scope = viewer_scope(request, cluster_id)
        now = datetime.now(UTC)
        rows = [enrich(cr, now, grace) for cr in store.groupsyncs(cluster_id)]
        if scope == "self":
            # A projection into new dicts, never a mutation: the wide branch must keep
            # returning the store's own rows untouched.
            rows = [
                {field: cr[field] for field in SELF_TIER_GROUPSYNC_FIELDS}
                for cr in rows
            ]
        return rows

    @app.get("/api/clusters/{cluster_id}/groupsyncs/{name}/events")
    @consistent
    def list_events(
        request: Request,
        cluster_id: str,
        name: str,
        since: str | None = Query(
            default=None,
            description="ISO-8601 UTC instant; return only events observed after it"),
        limit: int = Query(
            default=200, ge=1, le=2000,
            description="Maximum events to return, newest first. `truncated` says whether "
                        "older ones were dropped."),
    ) -> dict:
        """Observed sync events for one GroupSync CR, newest first.

        Accumulated from polling rather than fetched, so the window starts when this
        dashboard did — see `note` in the response.
        """
        require_cluster(cluster_id)
        # limit + 1 to learn whether more exist, then hand back only `limit`. The cheap half
        # of R3 in docs/api-contract.md: it answers "is this all of them?" without a COUNT
        # over a table that grows with every poll, and it is the idiom list_users already
        # uses — one paging shape in the codebase rather than two.
        rows = store.sync_events(cluster_id, name, since, limit + 1)
        truncated = len(rows) > limit
        events = rows[:limit]
        return {
            "cluster": cluster_id,
            # FULL VIEW AT BOTH TIERS, by ruling (spec Q3): a sync timeline names CRs and
            # counts, never a person, and per-CR state is public on /metrics already.
            "scope": "all",
            "viewer": trusted_viewer(request),
            "groupsync": name,
            "count": len(events),
            "limit": limit,
            "truncated": truncated,
            # The timeline is accumulated, not fetched — it only covers the period this
            # dashboard has been running (PLAN §2). Saying so stops an empty list being
            # read as "the operator never synced".
            "note": "accumulated from polling; covers only the period since this dashboard started",
            # Where retention has cut the timeline, if anywhere. Cluster-wide: the edge is a
            # property of the policy, not of this CR.
            "retention": history_retention("sync_event", store.history_retained_since(cluster_id)),
            "events": events,
        }

    @app.get("/api/clusters/{cluster_id}/groups")
    def list_groups(
        request: Request,
        cluster_id: str,
        state: str = Query(
            default="all", pattern="^(all|empty|unattributed)$",
            description="`all`; `empty` for groups with zero members, whatever created them; "
                        "`unattributed` for groups no GroupSync CR claims. The two overlap: a "
                        "hand-made group with no members is both."),
    ) -> dict:
        """Synced groups on one cluster, optionally narrowed to a problem state.

        SELF-SCOPED under view restrictions: a plain reader sees only the groups they are
        a member of, because they do not pass the wide-tier review — `list clusterrolebindings`
        by default (measured: `no` for every plain persona on the lab, with their real group
        memberships supplied to the review). An object rather
        than the bare list this used to be, so `scope` and `viewer` ride the response and
        the UI never has to derive the tier — the activity-endpoint contract.
        """
        require_cluster(cluster_id)
        viewer, scope = viewer_scope(request, cluster_id)
        rows = store.groups(
            cluster_id, state,
            user_name=None if scope == "all" else require_viewer(viewer, cluster_id),
        )
        return {
            "cluster": cluster_id,
            "scope": scope,
            "viewer": viewer,
            "count": len(rows),
            "groups": rows,
        }

    @app.get("/api/clusters/{cluster_id}/groups/{name}")
    @consistent
    def group_detail(request: Request, cluster_id: str, name: str) -> dict:
        """One group: its members, the CR that syncs it, and what it grants.

        A group with history but no current state is reported as DELETED rather than 404 —
        it is still named by every membership-change row that mentions it.

        SELF-SCOPED under view restrictions: only groups the viewer belongs to. The
        member check runs BEFORE any existence lookup, so a non-member's 403 is constant
        for a real group and a nonexistent one alike — answering differently would be a
        per-name existence oracle over the very list the self tier withholds. A member
        sees the full detail: membership is the entitlement, and their group's roster is
        exactly what they can see about themselves in the directory. Deleted groups are
        unreachable at self by the same rule — no membership row, no view — which fails
        closed rather than resurrecting history for an ex-member.
        """
        require_cluster(cluster_id)
        viewer, scope = viewer_scope(request, cluster_id)
        if scope == "self" and not store.is_group_member(
            cluster_id, name, require_viewer(viewer, cluster_id)
        ):
            raise HTTPException(
                status_code=403,
                detail="this group is outside your view; group detail beyond your own "
                       "memberships needs the wide tier",
            )
        detail = store.group_detail(cluster_id, name)
        if detail is None:
            # A group we have history for but no current state is DELETED, not unknown.
            # It is still reachable from every membership-change row that mentions it, and
            # "this group no longer exists, here is who was in it and when it went" is the
            # answer to that click — 404 strands the reader on a dead end instead.
            history = store.membership_events(cluster_id, group_name=name, limit=100)
            if not history:
                raise HTTPException(status_code=404, detail=f"unknown group {name!r}")
            return {
                "name": name,
                "scope": scope,
                "viewer": viewer,
                "deleted": True,
                "member_count": 0,
                "sync_provider": None,
                "group_synced_at": None,
                "ldap_uid": None,
                "observed_at": None,
                "owner": None,
                "members": [],
                "changes": history,
                "retention": history_retention("membership_event", store.history_retained_since(cluster_id)),
                "bindings": store.group_bindings(cluster_id, name),
            }
        detail["deleted"] = False
        owner = None
        if detail.get("sync_provider"):
            for cr in store.groupsyncs(cluster_id):
                if detail["sync_provider"] in (cr.get("provider_keys") or []):
                    owner = {"name": cr["name"], "namespace": cr["namespace"],
                             "schedule": cr["schedule"]}
                    break
        return {
            **detail,
            "scope": scope,
            "viewer": viewer,
            "owner": owner,
            "members": store.group_members(cluster_id, name),
            "changes": store.membership_events(cluster_id, group_name=name, limit=100),
            "retention": history_retention("membership_event", store.history_retained_since(cluster_id)),
            # DIRECT bindings only. Role rules are never fetched or expanded, so this is
            # not an effective-permission calculation and must not be presented as one.
            "bindings": store.group_bindings(cluster_id, name),
        }

    @app.get("/api/clusters/{cluster_id}/users")
    @consistent
    def list_users(
        request: Request,
        cluster_id: str,
        limit: int = Query(
            default=1000, ge=1, le=10000,
            description="Maximum users to return. `truncated` says whether more exist; `total` is the whole set."),
        offset: int = Query(default=0, ge=0, description="Users to skip, for paging."),
    ) -> dict:
        """People who have logged in to this cluster, bounded and honest about it.

        One row per OpenShift User object, because the cluster creates one at first login through
        an identity provider and never before — so the row IS the fact of a login, and the
        headline count is how many people have used the cluster (docs/DESIGN_users_tab_logins.md).
        Group membership is an attribute of a row: `group_count` may be 0 for someone who logged
        in and holds no synced access. Members of synced groups who have never logged in are not
        rows; they are reported once, as `never_logged_in_members`, so a reviewer still gets the
        number and the names without them inflating the count.

        Per row: `logged_in` (false only for an account created by hand that nobody has used),
        `first_login_at` (the Identity object's creation time when `first_login_source` is `identity`,
        the User's creation time when it is `user`, null when `logged_in` is false; for a provider
        with `mappingMethod: lookup` an administrator creates the Identity before the first login,
        so an Identity-sourced time is that create), `providers` (identity-provider names),
        `last_login_at` (the newest successful captured
        login, null when none — read `login_capture` before trusting the null), `full_name`.
        `first_login_source` per row says whether `first_login_at` is the Identity's creation time
        (`identity`) or the User's (`user`, approximate); `identities_source` says why.

        `total` is every User object under the scope; `logged_in_total` is those with an identity —
        the people who have actually logged in — and is the headline number. They differ by the
        accounts created by hand (`logged_in: false`), which are listed but are not logins.

        `source` says whether the last poll could read the User objects: `ok`; `forbidden`, when
        the chart's `rbac.users` grant is missing, in which case the rows are stale or absent and the
        tab must say so rather than show an empty cluster; `pending` before the first poll.

        Paged, per R3: `total` is the whole set, `offset` and `limit` are this page. Fetches
        `limit + 1` to report `truncated` without trusting the count and the page to agree.

        SELF-SCOPED under view restrictions: a plain reader gets their own row or an empty list,
        because `list users.user.openshift.io` is a permission they do not hold — the only
        self-read OpenShift grants everyone is `get users/~`. The never-logged-in line is scoped
        the same way, so a narrowed reader learns nothing about anyone else.
        """
        require_cluster(cluster_id)
        viewer, scope = viewer_scope(request, cluster_id)
        who = None if scope == "all" else require_viewer(viewer, cluster_id)
        providers = settings.users_providers
        rows = store.users(cluster_id, limit=limit, offset=offset, user_name=who, providers=providers)
        never = store.synced_members_without_user(cluster_id, user_name=who)
        status = store.users_source(cluster_id)
        istatus = store.identities_source(cluster_id)
        return {
            "cluster": cluster_id,
            "scope": scope,
            "viewer": viewer,
            "source": (status or {}).get("state") or "pending",
            "source_observed_at": (status or {}).get("observed_at"),
            # Which provider names the list is narrowed to (config.users.providers); [] means all.
            # Applied to `users`, `total` and `logged_in_total`, NOT to never_logged_in_members: a
            # member who logged in through an excluded provider has logged in.
            "providers_filter": list(providers),
            # What first_login_at can be: ok (Identity objects read), forbidden (rbac.identities
            # not granted — rows fall back to the User time), off (the read is not switched on),
            # pending (switched on, no poll yet).
            "identities_source": (istatus or {}).get("state")
                                  or ("pending" if settings.identities_read_enabled else "off"),
            "identities_source_observed_at": (istatus or {}).get("observed_at"),
            "login_capture": "on" if settings.login_capture_enabled else "off",
            "total": store.count_users(cluster_id, user_name=who, providers=providers),
            "logged_in_total": store.count_users(cluster_id, user_name=who, logged_in_only=True,
                                                 providers=providers),
            "offset": offset,
            "limit": limit,
            "count": min(len(rows), limit),
            "truncated": len(rows) > limit,
            "never_logged_in_members": {"count": len(never), "names": never},
            "users": rows[:limit],
        }

    @app.get("/api/clusters/{cluster_id}/users/{name}")
    @consistent
    def user_detail(request: Request, cluster_id: str, name: str) -> dict:
        """Reverse lookup: every group this user is in.

        The cluster cannot answer this directly — it means scanning every Group object — yet
        it is the question behind most "why does this person have access?" investigations.

        SELF-SCOPED under view restrictions: their own profile only, refused BEFORE any
        store lookup so the 403 for a colleague and for a name that does not exist are
        byte-identical — otherwise this endpoint is a username oracle.
        """
        require_cluster(cluster_id)
        viewer, scope = viewer_scope(request, cluster_id)
        if scope == "self" and name != require_viewer(viewer, cluster_id):
            raise HTTPException(
                status_code=403,
                detail="user profiles other than your own need the wide tier",
            )
        groups = store.user_groups(cluster_id, name)
        changes = store.membership_events(cluster_id, user_name=name, limit=100)
        # The person as the Users tab knows them: None when no User object exists, i.e. they have
        # never logged in — a synced member reached from a group page, typically.
        record = store.user_record(cluster_id, name)
        # A user with no CURRENT groups is not unknown — they may have just been removed
        # from the last one, and "they are in nothing now" is the answer to the question,
        # not an error. And a User object with no groups at all is a person who logged in
        # and holds no synced access, which is a finding, not a 404. Only a name we have never
        # seen anywhere is unknown.
        if not groups and not changes and record is None:
            raise HTTPException(status_code=404, detail=f"unknown user {name!r}")
        return {
            "user": name,
            "cluster": cluster_id,
            "scope": scope,
            "viewer": viewer,
            # None whenever OpenShift has no name for them — no User object because they have
            # never logged in, or a User with fullName unset because their identity provider
            # supplies no name attribute. A separate store call rather than a join because this
            # handler is @consistent and already makes several inside one snapshot.
            "full_name": store.user_full_name(cluster_id, name),
            # The login facts, or null for a member who has never logged in. Same fields as a
            # row of /users, so the detail page and the list cannot disagree.
            "logged_in": bool(record and record["logged_in"]),
            "first_login_at": record["first_login_at"] if record else None,
            "first_login_source": record["first_login_source"] if record else None,
            "last_login_at": record["last_login_at"] if record else None,
            "providers": record["providers"] if record else [],
            "login_capture": "on" if settings.login_capture_enabled else "off",
            "groups": groups,
            "changes": changes,
            "retention": history_retention("membership_event", store.history_retained_since(cluster_id)),
            # Reachable through their group memberships. Each row carries via_group, so
            # "why do they have this?" is answerable without a second lookup.
            "bindings": store.user_bindings(cluster_id, name),
        }

    @app.get("/api/clusters/{cluster_id}/logins")
    @consistent
    def list_logins(
        request: Request,
        cluster_id: str,
        outcome: str | None = Query(
            default=None,
            # VALIDATED against the parser's own vocabulary, and this is what LOGIN_OUTCOMES is
            # for — it was computed and then read by nothing, so the guarantee its comment
            # promised did not exist. An unknown value used to return HTTP 200 with zero
            # attempts, which is byte-identical to a valid filter that genuinely matches
            # nothing: `outcome=bad_pasword` read as "no failed logins" in a tool whose whole
            # job is telling you when there ARE some. 422 now, matching /groups' `state`.
            #
            # Derived rather than restated so a new outcome in loginlog.py becomes queryable
            # the moment it can be parsed, instead of being rejected by a second list nobody
            # remembered to extend. The derived values are regex-escaped at construction: a
            # future literal containing punctuation must remain one literal outcome.
            pattern=LOGIN_OUTCOME_PATTERN,
            description="Return only attempts with this outcome. The vocabulary is the parser's: "
                        "success, bad_password, rejected (not found OR not permitted — the log "
                        "cannot tell those apart), password_expired, must_change_password, "
                        "account_locked, account_disabled, account_expired, logon_not_permitted, "
                        "and failed (the provider gave no reason — the normal shape on an "
                        "HTPasswd provider, which logs a verdict and nothing else)."),
        user: str | None = Query(
            default=None,
            description="Only attempts for this exact username — the login that was TYPED, which "
                        "may match no User object and no group member. That mismatch is a finding, "
                        "not an error."),
        kind: str = Query(
            default="credential,cli",
            pattern=r"^(credential|cli|session|all)(,(credential|cli|session|all))*$",
            description="Which kinds of attempt, comma-separated: credential (the interactive "
                        "form — every pod-log row is one), cli (`oc login` and other "
                        "openshift-challenging-client logins), session (an existing session "
                        "re-authorising to a client such as the console or this dashboard — the "
                        "audit-log source only), or all. Default credential,cli: sessions are "
                        "not new logins and are shown on request."),
        limit: int = Query(
            default=200, ge=1, le=2000,
            description="Maximum attempts returned, newest first. `truncated` says whether older "
                        "ones were dropped; `total` and `summary` always describe the whole "
                        "retained record, never this page."),
    ) -> dict:
        """Login attempts against this cluster's oauth-server: who, when, and why it failed.

        Rows carry `source` (pod-log or audit-log), `kind`, and — from the audit-log source — the
        OAuth `client_id` a cli/session row authorised to, `identity_match` (the configured
        provider the typed name resolves to through the User's Identity, or null: kept, visibly
        unmatched), and what the record says about a failure: `status_code` and `error_message`
        (the audit log records no cause beyond those; a browser failure is a 302 back to the form).

        THE RECORD IS A WINDOW, and both of its edges are carried as data rather than implied.
        `capture_started_at` is when watching began and is stable; `retained_since` is the oldest
        attempt still kept and moves under retention. Nothing before capture began exists to fetch —
        the log dies with its pod — so an empty list is a statement about the window and never proof
        that nobody logged in. The UI has to say that, which is why it is here and not a footnote.

        EVERY username is recorded, successful or not, member or not. `known_user: false` marks an
        account in NO synced group, which is the most valuable row this produces; `has_history: true`
        separates "access was removed and they are still trying" from "nobody ever governed this
        name". `ungoverned` lists those accounts separately so a paged chronology cannot bury them.
        """
        require_cluster(cluster_id)
        # THE MOST SENSITIVE ENDPOINT IN THE APPLICATION (requirements §2): it names people
        # and states that their password was wrong or their account locked. SELF-SCOPED
        # under view restrictions, and byte-exact on purpose: the capture stores the name
        # AS TYPED (measured live: rows for both `lateef.o` and `LATEEF.O`), while the
        # viewer arrives in the directory form, so a case-variant attempt stays visible to
        # the wide tier only. A COLLATE NOCASE match was measured to degrade the query to
        # the cluster-wide index scan AND would cross-leak between two OpenShift Users
        # differing only by case — User names are case-sensitive.
        viewer, scope = viewer_scope(request, cluster_id)
        if scope == "self":
            me = require_viewer(viewer, cluster_id)
            if user is not None and user != me:
                raise HTTPException(
                    status_code=403,
                    detail="login attempts other than your own need the wide tier",
                )
            user = me
        # Which provider NAMES are HTPasswd is deployment configuration — the log carries only the
        # name. Passed to the ungoverned queries so their rows and their count share ONE predicate in
        # the store, and applied per row below for the break_glass label.
        htpasswd = tuple(settings.login_capture_htpasswd_providers)
        status = store.login_capture_status(cluster_id)
        # Computed at BOTH tiers: the self view keeps the window edges (capture_started_at,
        # retained_since — facts about the record, not about a person) and withholds the
        # personnel aggregates below.
        summary = store.login_event_summary(cluster_id, exclude_providers=htpasswd)
        ungoverned = (
            store.ungoverned_login_users(cluster_id, exclude_providers=htpasswd, limit=50)
            if scope == "all" else None
        )
        # limit + 1 to learn whether more exist — the list_users idiom. `summary` carries the exact
        # whole-record numbers, so no headline figure is ever computed from this page.
        kinds = None if "all" in kind.split(",") else tuple(dict.fromkeys(kind.split(",")))
        rows = store.login_events(cluster_id, user_name=user, outcome=outcome, limit=limit + 1,
                                  kinds=kinds)
        truncated = len(rows) > limit
        attempts = rows[:limit]

        by_outcome = summary["by_outcome"]
        successes = by_outcome.get(loginlog.OUTCOME_SUCCESS, 0)
        # Gate membership for the names on this page, in ONE batch lookup rather than a call per row.
        # An empty dict means no gate is known, and the rows then carry None — "unknown", which is a
        # different statement from False and the reason a `rejected` row can only sometimes be
        # explained. With a gate known, `in_access_group: false` on a person who IS in a synced group
        # turns "not found OR not permitted" into "a real person, not gated".
        gate = store.is_in_access_group(cluster_id, [r["user_name"] for r in attempts])
        for row in attempts:
            # Normalised here so the UI never re-derives a flag from raw fields, and so the wire
            # carries real booleans whatever 0/1 shape SQLite returned.
            row["break_glass"] = row.get("provider") in htpasswd
            row["known_user"] = bool(row.get("known_user"))
            row["has_history"] = bool(row.get("has_history"))
            # None, not False, when no gate is known. The UI must be able to say "we cannot tell"
            # rather than asserting a non-membership it has no basis for.
            row["in_access_group"] = gate.get(row["user_name"])
            row["refusal_reason"] = _refusal_reason(row)
        for row in ungoverned or []:
            row["has_history"] = bool(row.get("has_history"))

        return {
            "cluster": cluster_id,
            "scope": scope,
            "viewer": viewer,
            "enabled": settings.login_capture_enabled,
            # Which log the rows come from, and what that source can and cannot say — the two
            # differ in exactly the ways a reader of this page needs to know (no cause from the
            # audit log; no history from the pod log).
            "source": settings.login_capture_source,
            "kinds": list(kinds) if kinds else ["credential", "cli", "session"],
            "note": (
                "read from the oauth-server audit log on the control-plane nodes: no Debug "
                "verbosity needed, and history back to the oldest rotated audit file on a first "
                "read. Every attempt is a row — credential logins, CLI logins and, on request, "
                "session re-authorisations — with the identity provider the typed name resolves "
                "to. The audit log records no cause for a refusal beyond the HTTP status and, "
                "for CLI failures, 'Authentication failed'; rows older than the configured "
                "retention age out"
                if settings.login_capture_source == "audit-log" else
                "read from the oauth-server log at Debug verbosity; covers only the period "
                "since capture began — earlier logins were never recorded and cannot be "
                "fetched, and rows older than the configured retention age out"
            ),
            # Set once by the capture loop's first successful read. Falls back to the oldest retained
            # attempt for the one-cycle window after a crash before that row exists — an honest floor
            # rather than null, which the UI would have to render as "unknown".
            "capture_started_at": (status or {}).get("started_at") or summary["first_at"],
            "last_read_at": (status or {}).get("last_read_at"),
            # How often `last_read_at` is EXPECTED to advance — capture runs on the poll thread, so
            # the poll interval is its cadence. Sent because the browser is the only place that can
            # decide whether a read is overdue and the only place that knows what a reader is
            # looking at, but it has no way to learn the cadence: a hardcoded threshold in the page
            # would call a 900s poll "stalled" every single cycle.
            "read_interval_seconds": settings.poll_interval_seconds,
            "retained_since": summary["first_at"],
            # At self, the whole-record count OF THE VIEWER (one indexed scalar), never the
            # cluster-wide total — a number computed over rows the response withholds would
            # be the count-versus-page defect reintroduced deliberately.
            "total": summary["total"] if scope == "all" else
                     store.count_login_events(cluster_id, user),
            "limit": limit,
            "truncated": truncated,
            # The personnel aggregates are WITHHELD at self, as None rather than zeros:
            # failure counts, distinct users and the ungoverned list are personnel data
            # even without names (the gsd_dashboard_active_users removal is the precedent),
            # and a fabricated 0 would read as "nothing happened". Never recomputed over
            # the visible subset either — "distinct users among yourself" is 1 by
            # construction, a number whose label would lie.
            "summary": {
                "distinct_users": summary["distinct_users"],
                "successes": successes,
                "failures": summary["total"] - successes,
                "by_outcome": by_outcome,
                "ungoverned_users": summary["ungoverned_users"],
                "first_at": summary["first_at"],
                "last_at": summary["last_at"],
            } if scope == "all" else None,
            # One row per account in no synced group, most recent first. Bounded at 50 and honest
            # about it: summary.ungoverned_users beside it is the whole-set count, from the SAME
            # store predicate, so the two cannot disagree.
            "ungoverned": ungoverned,
            "attempts": attempts,
        }

    @app.get("/api/clusters/{cluster_id}/cluster-access")
    @consistent
    def cluster_access(
        request: Request,
        cluster_id: str,
        limit: int = Query(
            default=200, ge=1, le=2000,
            description="Maximum rows per list. `summary` always describes the whole cluster."),
    ) -> dict:
        """Who can actually LOG IN, against who holds access — two different questions.

        Every other view in this dashboard starts from RBAC and stops there, so a role granted to
        somebody who cannot authenticate is invisible: access that can never be used. On the reference
        cluster 10 people held access through synced groups and 7 were in the gate group, so 3 held
        access they could not exercise.

        THE ANSWER DEPENDS ON A PREREQUISITE THIS DASHBOARD CANNOT MEET ITSELF. The gate group has to
        be synced into OpenShift by the group-sync-operator before there is any membership to compare
        against, and `synced: false` says the DN is known and the Group is not there. That is not zero
        findings — it is no data, and the two must never look alike.
        """
        require_cluster(cluster_id)
        viewer, scope = viewer_scope(request, cluster_id)
        access = store.cluster_access_group(cluster_id)
        if scope == "self":
            # THE VIEWER'S OWN GATE STATUS and nothing about anyone else. The DN, the
            # discovery source and both people-lists are withheld — the lists are other
            # people's findings, and the DN maps the directory. Withheld values are None,
            # never fabricated zeros: a summary of zeros would read as "no findings" to a
            # reader who cannot know it was narrowed. `in_access_group` is None when no
            # synced gate group exists to compare against — "we cannot tell" is a
            # different statement from "not a member", same contract as the logins rows.
            me = require_viewer(viewer, cluster_id)
            gated = bool(access)
            synced = bool(access and access["group_name"])
            membership = store.is_in_access_group(cluster_id, [me])
            return {
                "cluster": cluster_id,
                "scope": "self",
                "viewer": viewer,
                "gated": gated,
                "dn": None,
                "source": None,
                "group_name": None,
                "synced": synced,
                "in_access_group": membership.get(me) if synced else None,
                "note": ("membership of the login-gate group is required to authenticate; "
                         "in_access_group is your own status against it"
                         if synced else
                         "no synced login-gate group is known on this cluster, so your "
                         "gate status cannot be determined"),
                "summary": None,
                "access_without_login": None,
                "login_without_access": None,
                "limit": limit,
                "truncated": False,
            }
        if not access:
            # NO GATE, which is itself a finding rather than an absence: with no membership clause in
            # any identity provider's filter, every account in the search base can sign in.
            return {
                "cluster": cluster_id,
                "scope": scope,
                "viewer": viewer,
                "gated": False,
                "dn": None,
                "source": None,
                "group_name": None,
                "synced": False,
                "note": "no login gate is known. Either no identity provider's filter carries a "
                        "memberOf/isMemberOf clause — in which case any account in its search base "
                        "can sign in — or the OAuth CR could not be read. Set clusterAccess.group to "
                        "state the group explicitly.",
                "summary": {"gated_members": 0, "with_access": 0,
                            "access_without_login": 0, "login_without_access": 0},
                "access_without_login": [],
                "login_without_access": [],
                "limit": limit,
                "truncated": False,
            }

        synced = bool(access["group_name"])
        # limit + 1 to learn whether more exist — the list_users idiom used throughout.
        without_login = store.access_without_login(cluster_id, limit=limit + 1)
        truncated = len(without_login) > limit
        for row in without_login:
            row["has_tried"] = bool(row.get("has_tried"))
            # GROUP_CONCAT hands back one comma-joined string; the wire carries a list, so the UI
            # never splits a delimited field. A group name cannot contain a comma (RFC 1123 label
            # rules apply to a Group's metadata.name), so the split is safe here and would not be on
            # an LDAP DN — which is exactly why user_name is never packed this way.
            row["groups"] = [g for g in (row.get("groups") or "").split(",") if g]
        gated_only = store.login_without_access(cluster_id, limit=limit)
        for row in gated_only:
            row["has_tried"] = bool(row.get("has_tried"))

        return {
            "cluster": cluster_id,
            "scope": scope,
            "viewer": viewer,
            "gated": True,
            "dn": access["dn"],
            # Which of the two produced it. An operator asking "why is this the wrong group?" needs to
            # know whether to change values.yaml or the identity provider.
            "source": access["source"],
            "group_name": access["group_name"],
            "synced": synced,
            "note": ("membership of this group is required to authenticate, so somebody outside it "
                     "cannot use any access they hold")
                    if synced else
                    ("the gate group's DN is known but no synced Group matches it, so there is no "
                     "membership to compare against. The group-sync-operator has to pull it — see "
                     "docs/examples/clusteraccess-groupsync.yaml. Note a gate group is often "
                     "objectClass groupOfUniqueNames with `uniqueMember`, unlike RBAC groups: "
                     "copying an existing CR's rfc2307 block verbatim syncs it with zero members."),
            "summary": store.cluster_access_summary(cluster_id),
            "access_without_login": without_login[:limit],
            "login_without_access": gated_only,
            "limit": limit,
            "truncated": truncated,
        }

    @app.get("/api/clusters/{cluster_id}/bindings/findings")
    @consistent
    def binding_findings(
        request: Request,
        cluster_id: str,
        limit: int = Query(
            default=500, ge=1, le=5000,
            description="Maximum bindings to return across all tiers. `counts` and `total` "
                        "always describe the whole cluster, not this page."),
        offset: int = Query(default=0, ge=0, description="Bindings to skip, for paging."),
    ) -> dict:
        """Every group-subject binding on a cluster, classified into five tiers.

        Three unresolved tiers rather than one: on a real cluster the large majority of
        unresolvable Group subjects are built-in virtual groups
        (`system:serviceaccounts:*`, `system:authenticated`), which authorise real access
        and have no object by design. Reporting those as broken buries the few that are.

        ADMINISTRATOR TIER ONLY, and this REVERSES an earlier ruling of ours. Spec Q3 called
        these rows "governance data about objects, not people" and served them at both tiers.
        That reasoning does not survive measurement: a binding row names which GROUP holds
        which ROLE, and on the reference cluster an ordinary reader who could not run any of
        `list clusterrolebindings`, `list rolebindings` or `list groups` was handed 236 rows,
        21 naming an admin role — a list of which groups to join to gain admin, obtainable
        here and not with `oc`. See require_admin_tier for the full measurement.

        The COUNTS remain public on /metrics (`gsd_bindings_total{finding=...}`) and that is
        unchanged and fine: an aggregate is not a target list. It is the rows that escalate.

        Each row also says who it REACHES: `member_count`, the named Group's own member count,
        and `logged_in_count`, how many of those members have logged in — a User object with an
        identity, the definition the Users tab uses. Both are null when no Group object exists
        (dangling, unresolved, built-in), so 0 keeps its meaning: the group exists and grants
        nobody today. A binding that names a role is not access until someone is in the group.
        """
        require_cluster(cluster_id)
        require_admin_tier(request, cluster_id)
        # Every binding, including the ones that resolve normally. A view labelled
        # "bindings" that omitted the healthy majority (74 of 228 here) misrepresented the
        # cluster; the caller filters, rather than the API deciding what is worth seeing.
        #
        # Bounded since: measured at 2,280 rows / 545,800 bytes on a cluster ten times the
        # reference size, fetched on a 30-second auto-refresh — 5.3x the payload that got
        # list_users bounded. `counts` comes from a scalar query rather than from these
        # rows, so it keeps describing the cluster once the rows are a page of it.
        counts = store.count_bindings_by_finding(cluster_id)
        total = sum(counts.values())
        rows = store.all_bindings(cluster_id, limit=limit, offset=offset, reach=True)
        by_tier: dict[str, list[dict]] = {
            "ok": [], "dangling": [], "unresolved": [], "built_in": [], "unmanaged": []
        }
        for row in rows:
            by_tier.setdefault(row["finding"], []).append(row)
        return {
            "cluster": cluster_id,
            # Always "all", and now only ever REACHED at that tier — require_admin_tier
            # refuses above, so there is no narrowed variant of this payload to declare. The
            # person-named analogue, bindings that name a User directly, lives on
            # /user-bindings and is self-scoped there rather than refused, because a reader's
            # own grants are theirs to see.
            "scope": "all",
            "viewer": trusted_viewer(request),
            "note": "direct bindings only; role rules are not evaluated",
            "total": total,
            "limit": limit,
            "offset": offset,
            "truncated": offset + len(rows) < total,
            # From the scalar query, NOT from by_tier — by_tier holds this page. Counting
            # the page here is the defect that shipped twice already.
            "counts": {tier: counts.get(tier, 0) for tier in by_tier},
            # The policy operator that TEMPLATES these bindings, when installed. `present`
            # distinguishes "not installed" from "installed, zero CRs" so the UI never
            # renders all-healthy for a concept the cluster does not have.
            "operator_configs": store.operator_configs(cluster_id),
            **by_tier,
        }

    @app.get("/api/clusters/{cluster_id}/namespaces")
    @consistent
    def list_namespaces(request: Request, cluster_id: str) -> dict:
        """Every namespace the poller sees on one cluster, with its configured labels and two
        counts — distinct groups bound in it, and non-platform grants naming a person there
        (#167: the audit's picker offered only namespaces that already carried a grant; a
        namespace with none is the result a review wants to confirm).

        `source` says whether the namespace read was permitted: a refused read cannot attest
        absence, and the page says so instead of showing an empty list as a clean one.
        Cluster-wide bindings reach every namespace and are counted once on the envelope.

        SELF-SCOPED under view restrictions: only the namespaces the viewer's own memberships or
        own bindings reach, counted over those paths — "grants affecting them"
        (docs/ACCESS_CONTROL.md); the cluster-wide counts are the viewer's own, and an own
        cluster-wide path lists every namespace, as it reaches every one.
        """
        require_cluster(cluster_id)
        viewer, scope = viewer_scope(request, cluster_id)
        me = None if scope == "all" else require_viewer(viewer, cluster_id)
        groups = None if me is None else [g["group_name"] for g in store.user_groups(cluster_id, me)]
        # The cluster-wide rows — every one at the wide tier, the viewer's own at the self tier —
        # counted the way every row counts: DISTINCT groups (a group with a cluster-admin and a view
        # ClusterRoleBinding is one group), non-platform grants naming a person. A cluster-wide path
        # reaches every namespace, which is what namespace_reach answers for the detail; the list
        # says the same (review of #167: Codex and OB1 on the count, OB1 F2 on the self tier).
        wide = store.namespace_detail(cluster_id, "", user_name=me, groups=groups)
        cluster_wide_groups = len({g["group_name"] for g in wide["via_groups"] if not g["is_platform"]})
        cluster_wide_grants = len([d for d in wide["cluster_wide_grants"] if not d["is_platform"]])
        # The switch that lists every namespace is REACH — every cluster-wide binding naming the
        # viewer, a platform identity's included — the same rule namespace_reach applies to the
        # detail. The two counts stay the review's counts, platform identities left out; the page
        # explains the one case where they differ (review of #167, pass 2, Codex).
        cluster_wide_path = bool(wide["via_groups"] or wide["cluster_wide_grants"])
        rows = store.namespaces(cluster_id, user_name=me, groups=groups, every=cluster_wide_path)
        source = store.namespaces_source(cluster_id)
        return {
            "cluster": cluster_id,
            "scope": scope,
            "viewer": viewer,
            "source": {"state": source["state"], "observed_at": source["observed_at"]} if source else None,
            "label_keys": list(settings.namespace_metadata_labels),
            "count": len(rows),
            "cluster_wide_groups": cluster_wide_groups,
            "cluster_wide_grants": cluster_wide_grants,
            "cluster_wide_path": cluster_wide_path,
            "namespaces": rows,
        }

    @app.get("/api/clusters/{cluster_id}/namespaces/{name}")
    @consistent
    def namespace_detail(request: Request, cluster_id: str, name: str) -> dict:
        """One namespace: its labels, who reaches it and through which group, the grants naming
        a person there, the cluster-wide grants that reach it too, its siblings under the first
        configured label, and its history of binding changes (#167).

        A namespace the store no longer holds but that bindings or history still name is
        answered with `present: false`, not 404'd — a removed namespace's link is a detour, not a
        dead end. 404 only when nothing at all names it.

        SELF-SCOPED under view restrictions: refused BEFORE any lookup unless one of the
        viewer's own paths reaches the namespace, so the 403 for a namespace outside their view
        and for one that does not exist are byte-identical — no existence oracle over the very
        list the self tier withholds. Then the viewer's own paths only; `people` is withheld as
        None, being a count over other people's memberships.
        """
        require_cluster(cluster_id)
        viewer, scope = viewer_scope(request, cluster_id)
        me = None if scope == "all" else require_viewer(viewer, cluster_id)
        groups = None
        if me is not None:
            groups = [g["group_name"] for g in store.user_groups(cluster_id, me)]
            if not store.namespace_reach(cluster_id, name, me, groups):
                raise HTTPException(
                    status_code=403,
                    detail="this namespace is outside your view; namespace detail beyond your own "
                           "grants needs the wide tier",
                )
        keys = list(settings.namespace_metadata_labels)
        detail = store.namespace_detail(cluster_id, name, user_name=me, groups=groups,
                                        sibling_key=keys[0] if keys else None)
        history = store.binding_events(cluster_id, namespace=name, limit=100, viewer=me, viewer_groups=groups)
        if not detail["present"] and not detail["via_groups"] and not detail["direct_grants"] and not history:
            raise HTTPException(status_code=404, detail=f"unknown namespace {name!r}")
        return {
            "cluster": cluster_id,
            "scope": scope,
            "viewer": viewer,
            "label_keys": keys,
            **detail,
            "changes": history,
            "retention": history_retention("binding_event", store.history_retained_since(cluster_id)),
        }

    @app.get("/api/clusters/{cluster_id}/home")
    @consistent
    def home(request: Request, cluster_id: str) -> dict:
        """Home — the viewer's own access on one cluster, the page every reader lands on (#158).

        SELF-SCOPED BY DEFINITION, on every tier: an administrator sees their own access here, never
        everyone's, so the payload for a name is the same whichever tier resolves it. The identity is
        the proxy's; without one there is nothing to scope to and the request is refused — never a
        name the caller typed. Composed from the reads the drill-downs already serve (the viewer's
        groups, the bindings those groups reach, the bindings naming them directly, their membership
        history), and the arithmetic behind the page's sentences lives in gsd/home.py so a number and
        its label change together. `elsewhere` names the other enabled clusters that treat this
        identity as their own — a cluster whose identity policy withholds the host's username is not
        listed, since nobody vouched for the name there.
        """
        require_cluster(cluster_id)
        viewer, scope = viewer_scope(request, cluster_id)
        me = require_viewer(viewer, cluster_id)
        groups = store.user_groups(cluster_id, me)
        via = store.user_bindings(cluster_id, me)
        direct = store.direct_user_bindings(cluster_id, include_platform=True, user_name=me)
        record = store.user_record(cluster_id, me)
        since = (datetime.now(UTC) - timedelta(days=HOME_CHANGES_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
        # Each cluster's history is capped, so a card that showed the count as complete would be
        # overclaiming on a busy one: the clusters that hit the cap ride along and the page says so
        # (review of #158, Codex).
        capped: list[str] = []
        own = store.membership_events(cluster_id, user_name=me, limit=HOME_EVENTS_LIMIT)
        if len(own) >= HOME_EVENTS_LIMIT:
            capped.append(cluster_id)
        events = [dict(e, cluster=cluster_id) for e in own]
        counts = store.memberships_by_cluster(me)
        elsewhere = []
        for c in store.clusters():
            if c["id"] == cluster_id or not is_served(c["id"]) or not vouches_for_host_identity(c["id"]):
                continue
            n = counts.get(c["id"], 0)
            if not n:
                continue   # "you're also on" means a membership there; a cluster with none is not theirs
            elsewhere.append({"cluster": c["id"], "memberships": n, "status": c["status"], "last_poll": c["last_poll"]})
            theirs = store.membership_events(c["id"], user_name=me, limit=HOME_EVENTS_LIMIT)
            if len(theirs) >= HOME_EVENTS_LIMIT:
                capped.append(c["id"])
            events += [dict(e, cluster=c["id"]) for e in theirs]
        return {
            "cluster": cluster_id,
            "viewer": me,
            "scope": scope,
            "full_name": store.user_full_name(cluster_id, me),
            "providers": record["providers"] if record else [],
            "answer": derive_answer(groups, via, direct),
            "direct": direct,
            "changes": dict(group_changes(events, since), capped_clusters=sorted(capped)),
            "retention": history_retention("membership_event", store.history_retained_since(cluster_id)),
            "elsewhere": elsewhere,
            "memberships_total": counts.get(cluster_id, 0) + sum(e["memberships"] for e in elsewhere),
        }

    @app.get("/api/clusters/{cluster_id}/user-bindings")
    @consistent
    def direct_user_bindings(
        request: Request,
        cluster_id: str,
        include_platform: bool = Query(
            default=False,
            description="Include cluster-internal identities (`system:*`, `kubeadmin`). "
                        "Excluded by default: there is nowhere to migrate them to, and on "
                        "the reference cluster they were 34 of 36 rows."),
        namespace: str | None = Query(
            default=None,
            description="restrict to one namespace; '(cluster-scoped)' for cluster-wide"),
        limit: int = Query(
            default=200, ge=1, le=5000,
            description="Maximum bindings to return, worst-privilege first. `total` is the "
                        "count before this limit."),
        offset: int = Query(
            default=0, ge=0, description="Bindings to skip, for paging through `total`."),
    ) -> dict:
        """Roles granted DIRECTLY to a user, with a per-namespace migration worklist.

        The governance violation this reports: access bound to a person instead of to an
        enterprise-managed group. It survives offboarding — removing someone from an LDAP
        group revokes their access everywhere, while a direct binding keeps granting to a
        name nobody reviews — and no group-based audit can see it.

        Cluster-internal identities (system:*, the kube components) and OpenShift's
        break-glass `kubeadmin` are excluded by default: there is nowhere to migrate them
        to, and on the reference cluster they were 34 of 36 rows, so including them would
        make the finding unreadable. `include_platform=true` shows them, and the count is
        always reported so the page can say what it left out.

        `bindings` IS PAGED; `by_namespace` IS NOT, and the asymmetry is deliberate. The
        rollup is one row per namespace, so it is bounded by a number the cluster already
        keeps small, and it is the view that actually answers "where is my exposure" — it
        must never be truncated or the risk ranking would be a ranking of an arbitrary
        subset. The flat binding list grows with people times grants, is the part that can
        reach thousands, and is a detail view nobody reads end to end. `total` is always
        the count BEFORE the limit so the page can state what it left out; a silently
        truncated audit list is worse than a slow one.

        @consistent because this makes four store calls. Without it the KPI counts, the
        per-namespace rollup and the paged rows can each land on a different snapshot, and
        a poll committing between them yields a page whose total disagrees with its own
        table.
        """
        require_cluster(cluster_id)
        # SELF-SCOPED under view restrictions: only bindings that name the viewer — their
        # own grants (requirements §2). Byte-exact against the subject name as the
        # administrator typed it, so a binding naming `jdoe` is invisible to `john.doe`:
        # fail-closed, because nothing proves those are one person. The rollup and the
        # platform count aggregate OTHER people's grants, so at self they are withheld as
        # None — never recomputed over one person (a one-row "worklist" would relabel the
        # migration effort as the viewer's) and never fabricated zeros.
        viewer, scope = viewer_scope(request, cluster_id)
        me = None if scope == "all" else require_viewer(viewer, cluster_id)
        total = store.count_direct_user_bindings(
            cluster_id, include_platform=include_platform, namespace=namespace,
            user_name=me)
        rows = store.direct_user_bindings(
            cluster_id, include_platform=include_platform, namespace=namespace,
            limit=limit, offset=offset, user_name=me)
        return {
            "cluster": cluster_id,
            "scope": scope,
            "viewer": viewer,
            "note": "direct user grants; migrate these to LDAP-managed groups",
            "by_namespace":
                store.user_bindings_by_namespace(cluster_id) if scope == "all" else None,
            "excluded_platform":
                store.platform_user_binding_count(cluster_id) if scope == "all" else None,
            "namespace": namespace,
            "total": total,
            "limit": limit,
            "offset": offset,
            "truncated": offset + len(rows) < total,
            "bindings": rows,
        }

    @app.get("/api/clusters/{cluster_id}/operator-configs")
    def operator_configs(request: Request, cluster_id: str) -> dict:
        """Health of the namespace-configuration-operator's CRs on this cluster.

        `present: false` means the CRDs do not exist there — auto-detected, and a
        different truth from "installed with zero CRs". Reconcile conditions only, by
        design: the templates are the operator's business.

        ADMINISTRATOR TIER ONLY. Spec Q3 served this at both tiers as "governance data about
        objects", and unlike the GroupSync CRs there is no /metrics analogue — nothing here is
        public, so the earlier reasoning left a genuinely private view open. It describes how
        this cluster's access is templated, which is administrator business and answers nothing
        a reader can ask about themselves. It renders on the Overview and RBAC policy tabs,
        both of which are the administrator tier now.
        """
        require_cluster(cluster_id)
        require_admin_tier(request, cluster_id)
        return {
            "cluster": cluster_id,
            "scope": "all",
            "viewer": trusted_viewer(request),
            **store.operator_configs(cluster_id),
        }

    @app.get("/api/clusters/{cluster_id}/kyverno")
    @consistent
    def kyverno(
        request: Request,
        cluster_id: str,
        problems: bool = Query(default=True, description="Only fail/warn/error results (the page's default); false lists every result."),
        controlled: bool = Query(default=False, description="Include results on Pods, ReplicaSets and Jobs — usually a "
                                                            "controller's copies of one finding; off by default, said on the page."),
        # 63 + "/" + 253: a namespaced policy's wire string is `namespace/name`, both parts DNS names at their maxima (OB3)
        policy: str | None = Query(default=None, max_length=317, description="Only one policy's results (its wire string: "
                                                                            "namespace/name for a namespaced policy)."),
        kind: str | None = Query(default=None, pattern=r"^[A-Za-z]{1,40}$", description="With `policy`, the policy's kind — "
                                                                                       "a ValidatingPolicy and a MutatingPolicy may share a name."),
        limit: int = Query(default=500, ge=1, le=5000, description="Maximum result rows; `total` says how many match."),
    ) -> dict:
        """The Kyverno policy module (#165, #170): the CEL policies, their reports' results, the history.

        Three states the page must render distinctly: `present: null` (never polled since the
        module arrived), `present: false` (no policy-report API group is served — not installed),
        and `present: true` with `legacy_results` saying how many results the deprecated family
        wrote that this module does not read, and `breaker_drops` saying whether the reports
        controller dropped reports (null: no drop observed, or no scrape configured).

        ADMINISTRATOR TIER ONLY, like the operator configs: a policy finding names a resource and
        says what is wrong with it, cluster-wide, and answers nothing a reader can ask about
        themselves.
        """
        require_cluster(cluster_id)
        require_admin_tier(request, cluster_id)
        summary = store.kyverno_summary(cluster_id)
        # `breaker_configured` lets the page tell "kyverno.metricsUrl is not set" from "set, and the last scrape
        # failed": both leave the breaker fields null, and only one of them is a configuration gap (OB3).
        out = {"cluster": cluster_id, "scope": "all", "viewer": trusted_viewer(request),
               "enabled": settings.kyverno_enabled, "breaker_configured": bool(settings.kyverno_metrics_url), **summary}
        if summary.get("present"):
            rows, total = store.kyverno_results(cluster_id, problems_only=problems, include_controlled=controlled,
                                                policy=policy, kind=kind, limit=limit)
            out.update({"policies_list": store.kyverno_policies(cluster_id), "rows": rows, "total": total,
                        "truncated": len(rows) < total, "events": store.kyverno_events(cluster_id),
                        "controlled_kinds": list(CONTROLLED_KINDS)})
        return out

    @app.get("/api/clusters/{cluster_id}/membership-changes")
    @consistent
    def membership_changes(
        request: Request,
        cluster_id: str,
        limit: int = Query(
            default=100, ge=1, le=1000,
            description="Maximum changes to return, newest first. `truncated` says whether "
                        "older ones were dropped."),
    ) -> dict:
        """Who joined or left which group, newest first.

        The only record of a departure: the cluster shows current membership, so once
        somebody is removed nothing on it says they were ever there. Accumulated from
        polling, so the window starts when this dashboard did.

        SELF-SCOPED under view restrictions: only the changes affecting the viewer
        (requirements §2) — the rows are person-by-person history, and the store already
        takes user_name as the privacy scope (membership_event_by_user serves it).
        """
        require_cluster(cluster_id)
        viewer, scope = viewer_scope(request, cluster_id)
        # limit + 1, as in list_events — see docs/api-contract.md R3. This log previously
        # cut off at 100 with nothing saying so, which on an audit trail reads as "no
        # further changes" rather than "not shown".
        rows = store.membership_events(
            cluster_id,
            user_name=None if scope == "all" else require_viewer(viewer, cluster_id),
            limit=limit + 1,
        )
        truncated = len(rows) > limit
        events = rows[:limit]
        return {
            "cluster": cluster_id,
            "scope": scope,
            "viewer": viewer,
            "count": len(events),
            "limit": limit,
            "truncated": truncated,
            "note": "accumulated from polling; covers only the period since this dashboard started",
            "retention": history_retention("membership_event", store.history_retained_since(cluster_id)),
            "changes": events,
        }

    @app.get("/api/clusters/{cluster_id}/binding-changes")
    @consistent
    def binding_changes(
        request: Request,
        cluster_id: str,
        namespace: str | None = Query(
            default=None,
            description="Only bindings in this namespace; the empty string selects "
                        "ClusterRoleBindings. Omit for every scope."),
        limit: int = Query(
            default=100, ge=1, le=1000,
            description="Maximum changes to return, newest first. `truncated` says whether "
                        "older ones were dropped."),
    ) -> dict:
        """Which (binding, subject) rows appeared or disappeared, newest first — the bindings'
        membership-changes (#167).

        The only record of a binding change: the current-state tables are replaced every
        refresh, so a RoleBinding created and deleted between two refreshes never existed as
        far as the cluster view is concerned. Accumulated from polling; a `baseline` row is the
        cluster's first observation, not a change anyone made.

        SELF-SCOPED under view restrictions: only rows naming the viewer, or a group the viewer
        belongs to — the same slice the drill-downs already serve them. The group list is read
        here, at the call site, so R5 counts it.
        """
        require_cluster(cluster_id)
        viewer, scope = viewer_scope(request, cluster_id)
        if scope == "all":
            rows = store.binding_events(cluster_id, namespace=namespace, limit=limit + 1)
        else:
            me = require_viewer(viewer, cluster_id)
            mine = [g["group_name"] for g in store.user_groups(cluster_id, me)]
            rows = store.binding_events(
                cluster_id, namespace=namespace, limit=limit + 1, viewer=me, viewer_groups=mine)
        truncated = len(rows) > limit
        events = rows[:limit]
        return {
            "cluster": cluster_id,
            "scope": scope,
            "viewer": viewer,
            "count": len(events),
            "limit": limit,
            "truncated": truncated,
            "baseline_rows": sum(1 for e in events if e.get("baseline")),
            "note": "accumulated from binding refreshes; a baseline row is the first observation, not a change",
            "retention": history_retention("binding_event", store.history_retained_since(cluster_id)),
            "changes": events,
        }

    @app.get("/api/alerts")
    @consistent
    def list_alerts(request: Request) -> dict:
        """Everything currently worth a human's attention, across all clusters.

        Ordered by severity. Derived per request from the same stored observations the rest
        of the API serves, so an alert here always has a page behind it.

        THAT INVARIANT IS WHAT SCOPES THIS FEED. Under view restrictions the self tier
        receives only the kinds in SELF_ALERT_DETAILS — the ones whose backing pages it
        sees — filtered by kind rather than recomputed, with each kind's detail policy
        applied in the same pass (reconcile_error keeps its kind and loses its text; the
        detail copies the CR's error_message, which /groupsyncs withholds at self). The
        response says so: an alert feed that quietly dropped rows would train readers
        that green means healthy when it means hidden. An object rather than the bare
        list this used to be, so `scope` and `viewer` ride the wire (the activity
        contract).
        """
        # The envelope's viewer is the name; the decisions are made per cluster below, so a
        # nameless decision here only counted the host twice (review of D2, second pass).
        viewer = trusted_viewer(request)
        now = datetime.now(UTC)
        # B4's cliff policy, kept through the per-cluster rewrite: SPEC_D2's block predates it
        # (deviation recorded there). Named `cliff`, because the loop below binds `policy` to
        # each cluster's visibility policy.
        cliff = st.cliff_policy(settings)
        alerts: list[dict] = []
        # The feed's scope is the NARROWEST decision across the clusters it carries: "all" only
        # when every served cluster is wide for this reader. A feed that said "all" while one
        # cluster's rows were filtered would be the quiet-drop the response exists to name.
        scope = TIER_ALL
        served = False
        for row in store.clusters():
            cluster_id = row["id"]
            # A retired/disabled cluster's frozen snapshot must not keep producing "overdue" alerts
            # (#96): it is not served, so it does not contribute to the feed.
            if not row["enabled"]:
                continue
            policy, _ = settings.cluster_policy(cluster_id)
            if policy == VISIBILITY_HIDDEN:
                continue
            served = True
            _, cscope = viewer_scope(request, cluster_id)
            if cscope != TIER_ALL:
                scope = TIER_SELF
            found: list[dict] = []
            if row["status"] and row["status"] != "ok":
                found.append(
                    {
                        "cluster": cluster_id,
                        "kind": row["status"],
                        "subject": cluster_id,
                        "detail": row["message"] or "cluster poll failed",
                        "severity": "critical",
                        # The two silence fields every alert carries (gsd/state.py#Alert);
                        # SPEC_D2's block predated B4 and dropped them (review of D2, Codex).
                        "silenced": False,
                        "silenced_by": None,
                    }
                )
                # A degraded cluster's cached rows are stale by definition; computing
                # group-level alerts from them would report yesterday's state as today's.
                alerts.extend(found if cscope == TIER_ALL else _alerts_for_self(found))
                continue
            computed = st.compute_alerts(
                cluster=cluster_id,
                groupsyncs=store.groupsyncs(cluster_id),
                operator_configs=store.operator_configs(cluster_id)["configs"],
                user_bindings=store.direct_user_bindings(cluster_id),
                groups=store.groups(cluster_id, "all"),
                groupsync_present=store.groupsync_present(cluster_id),
                now=now,
                grace=grace,
                count_changes=(
                    store.group_count_changes(cluster_id, cliff.since(now)) if cliff else None
                ),
                cliff=cliff,
            )
            found.extend(a.as_dict() for a in computed)

            # Only the `dangling` tier alerts. `built_in` is normal, and `unresolved`
            # cannot be distinguished from a group that simply has not synced yet, so
            # alerting on either would produce noise that trains people to ignore this.
            for binding in store.binding_findings(cluster_id):
                if binding["finding"] != "dangling":
                    continue
                where = (
                    f"namespace {binding['binding_namespace']}"
                    if binding["binding_namespace"]
                    else "cluster-wide"
                )
                found.append(
                    {
                        "cluster": cluster_id,
                        "kind": "dangling_binding",
                        "subject": binding["binding_name"],
                        "detail": (
                            f"{binding['binding_kind']} grants {binding['role_name']} {where} to "
                            f"group {binding['group_name']!r}, which the operator used to "
                            f"manage and no longer exists — this binding now grants nobody"
                        ),
                        "severity": "critical",
                        "silenced": False,
                        "silenced_by": None,
                    }
                )
            # Filtered PER CLUSTER, in the cluster's own tier: a host administrator's feed
            # carries a self-only remote's alerts at the self kinds only.
            alerts.extend(found if cscope == TIER_ALL else _alerts_for_self(found))
        # Zero served clusters is NOT a wide feed: with everything retired/disabled/hidden the fold
        # never ran, so `all` here would say "you are wide and the estate is green" while whoami
        # correctly reads `self` — the exact quiet-drop this feed's scope exists to name (#96, review).
        if not served:
            scope = TIER_SELF
        severity_rank = {"critical": 0, "warning": 1}
        alerts.sort(key=lambda a: (severity_rank.get(a["severity"], 9), a["cluster"], a["kind"]))
        return {
            "scope": scope,
            "viewer": viewer,
            "count": len(alerts),
            "alerts": alerts,
        }

    metrics_registry = build_registry(store, grace, elector,
                                      signals=signals, settings=settings,
                                      reporting_enabled=bool(settings.reporting_url),
                                      system=system_monitor.sampler, volume=system_monitor.volume)

    @app.get("/metrics")
    def metrics() -> Response:
        """Prometheus exposition, collected from the store on each scrape.

        Unauthenticated by design so a ServiceMonitor can scrape it, which is why the
        collector emits counts and states only — never a group or user name.
        """
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

        return Response(generate_latest(metrics_registry), media_type=CONTENT_TYPE_LATEST)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    def kpi_links() -> dict:
        """The doors out of the KPI page (#157). The console's URL is the chart's `console.url` when
        set, else what the poll thread discovered from openshift-config-managed/console-public; the
        Grafana URL is the chart's `grafana.url` when set, else the Route the poll thread found by
        `grafana.discovery.selector` in the pod's own namespace (the openshift-grafana chart's);
        `observe` is the console's namespace-workloads dashboard scoped to THIS pod's namespace.

        The namespace rides in the PATH (`/dev-monitoring/ns/<ns>?dashboard=<board>`), never only in
        the query string: the console sets its project selector from a `/ns/<name>` path segment
        (console-app detect-context/namespace.ts, `getNamespace(pathname)`) or from the user's
        last-used project, and the plugin's graph panels put THAT selector — not the board's
        `$namespace` variable — on the tenancy proxy's `namespace=` parameter
        (monitoring-plugin query-browser.tsx, `useActiveNamespace()`). The admin-perspective form
        `/monitoring/dashboards/<board>?project-dropdown-value=<ns>` only templates the PromQL, so
        a reader whose last project was "All Projects" got `namespace=` empty and prom-label-proxy's
        400 (measured 2026-09-19 as a `view`-only user; a cluster-admin never hits the tenancy proxy
        and never saw it). The dev-monitoring route redirects to the admin form with the selector
        already set — measured on 4.22 for both kinds of user."""
        console = settings.console_url or signals.console_url()
        grafana = settings.grafana_url or signals.grafana_url()
        links = {k: v for k, v in (("grafana", grafana),
                                   ("grafana_dashboard_uid", settings.grafana_dashboard_uid),
                                   ("console", console)) if v}
        if console:
            ns = own_namespace()
            links["observe"] = (f"{console}/dev-monitoring/ns/{quote(ns, safe='')}"
                                "?dashboard=dashboard-k8s-resources-workloads-namespace"
                                if ns else f"{console}/monitoring/dashboards")
        return links

    @app.get("/api/kpi")
    @consistent
    def kpi(request: Request) -> dict:
        """The KPI module's in-app surface (#156): every definition rendered as JSON — the public ones
        /metrics also carries and the internal ones it never does — the 30-day trends with their
        retention edge, the daily rollup's series, and both processes' self-reported system usage.

        ADMINISTRATOR TIER ONLY: the internal class counts people, and the trends aggregate the
        fleet's churn and logins, which is governance data about the clusters, not about the reader
        (the same reasoning as /operator-configs). Each block states its as-of, so a figure that
        differs from a signed report's — a snapshot taken earlier — is explained, not mysterious.
        """
        require_admin_tier(request)
        from .kpi import COMPONENT_DASHBOARD, Context
        from .kpi.render_json import page_payload
        served = tuple(row["id"] for row in store.clusters() if is_served(row["id"]))
        last_poll = {row["id"]: row["last_poll"] for row in store.clusters()}
        ctx = Context(component=COMPONENT_DASHBOARD, system=system_monitor.sampler, volume=system_monitor.volume,
                      store=store, cluster_ids=served, signals=signals)
        report_system, report_system_at = signals.report_system()
        return {
            "scope": "all",
            "viewer": trusted_viewer(request),
            **page_payload(ctx, dashboard_system=system_monitor.view(), report_system=report_system,
                           report_system_at=report_system_at, last_poll=last_poll, grace=grace,
                           thresholds={"memory_percent": settings.kpi_memory_warn_percent,
                                       "cpu_percent": settings.kpi_cpu_warn_percent,
                                       "throttled_percent": settings.kpi_throttled_warn_percent,
                                       "disk_percent": settings.kpi_disk_warn_percent},
                           links=kpi_links()),
        }

    @app.get("/api/whoami")
    def whoami(request: Request) -> dict:
        """Who the proxy says this request is. Reflected, never stored by this endpoint.

        `authenticated` is false when the proxy is disabled even if a username is present,
        because in that mode the caller supplied it themselves. Every other field is gated
        on the same judgement, for the same reason: without the proxy there is no session
        to end and no idle timeout anyone enforces, so offering any of them would be the
        page claiming a security control that does not exist.

        ONE logout URL, the proxy's own sign_out, and it is composed from the configured
        prefix rather than hardcoded so a --proxy-prefix override cannot leave the page's
        control pointing at a path the proxy no longer answers.

        There was briefly a second, app-side URL that revoked the OAuth token first, the way
        the console's logout does. It was removed after MEASURING it fail: the console can
        revoke because its tokens carry scope `user:full`, while this chart authenticates
        through a ServiceAccount whose tokens carry `user:info` and `user:check-access` —
        neither of which permits a delete, so the API answered 403 regardless of RBAC. What
        remains is enough: the proxy clears its own cookie and re-entry demands credentials,
        measured on the reference cluster.

        `session` carries the CONFIGURED durations, never a deadline. Its `idle_timeout` is the same
        kind of thing — inputs to a model the browser runs, never a deadline the server knows. The session cookie is
        HttpOnly and the proxy forwards no session-age header, so the true expiry is not
        observable from here; these numbers are trustworthy only because the ConfigMap
        renders them from the same chart values as the proxy's own flags. The browser owns
        the countdown model built on them — see static/index.html.

        NEVER POLL THIS ON A SESSION-ONLY TIMER. Requesting it through the proxy re-stamps the
        session cookie like any other request, so a page calling it periodically would hold
        every session open forever — the exact defect the durations exist to fix. The page
        reads it once at load for its session controls; it also rides along in the ordinary
        data refresh, because `visibility` must follow live authorization changes, and that
        refresh is suspended by the browser's idle model while a countdown is up or expired.
        "Stay signed in" re-proves the session with one interaction-marked data refresh.
        `visibility` rides here so the page can LABEL its tier from the wire instead of
        deriving one — the UI never decides (tests/test_ui.py). Absent entirely when there
        is no authenticated identity: reporting a tier for a name nobody verified would
        lend that name credibility.
        """
        user = request.headers.get(USER_HEADER)
        authenticated = bool(user) and settings.oauth_proxy_enabled
        out = {
            "user": user if settings.oauth_proxy_enabled else None,
            "email": request.headers.get(EMAIL_HEADER) if settings.oauth_proxy_enabled else None,
            "authenticated": authenticated,
            # Composed, not hardcoded: tracks a --proxy-prefix override through
            # Settings.oauth_proxy_prefix so the link and the proxy cannot drift apart.
            "logout_url": (
                f"{settings.oauth_proxy_prefix}/sign_out" if authenticated else None
            ),
            "session": (
                {
                    "cookie_expire_seconds": settings.session_cookie_expire_seconds,
                    "cookie_refresh_seconds": settings.session_cookie_refresh_seconds,
                    # The idle-timeout MODEL's inputs, restated like the cap above and enforced
                    # here just as little: the page counts, and at zero sends the browser to
                    # logout_url. Present in both states so an operator can read the module's
                    # state off the wire; the page acts only on `enabled: true`.
                    "idle_timeout": (
                        {
                            "enabled": True,
                            "seconds": settings.session_idle_timeout_seconds,
                            "warning_seconds": settings.session_idle_timeout_warning_seconds,
                        }
                        if settings.session_idle_timeout_enabled
                        else {"enabled": False}
                    ),
                }
                if authenticated
                else None
            ),
        }
        if authenticated:
            # The tier from the SAME decision path the data handlers use — viewer_scope
            # reads the app.state seam per request and never raises — so the pill can
            # never disagree with the pages it sits above. An indeterminate tier is SELF.
            # PER CLUSTER, so the cluster selector can say which clusters this reader sees
            # narrowed (docs/ACCESS_CONTROL.md §11). Hidden clusters are absent, as they are
            # from /api/clusters — listing them here would undo the 404. The headline IS the
            # host row's decision: deciding it nameless and then again for the host counted
            # the host twice on gsd_visibility_decisions_total (review of D2, second pass).
            clusters: dict[str, dict] = {}
            host = settings.host_cluster()
            scope = None
            for c in settings.effective_clusters():
                # A disabled cluster is not served (#96): it must not appear in visibility.clusters
                # either, or whoami would name a cluster the selector and every tab omit.
                if not c.enabled:
                    continue
                policy, identity = settings.cluster_policy(c.name)
                if policy == VISIBILITY_HIDDEN:
                    continue
                _, cscope = viewer_scope(request, c.name)
                clusters[c.name] = {"policy": policy, "identity": identity, "scope": cscope}
                if host is not None and c.name == host.name:
                    scope = cscope
            if scope is None:            # no enabled cluster: the nameless question, fail-closed
                _, scope = viewer_scope(request)
            out["visibility"] = {
                "scope": scope,
                "enabled": settings.view_restrictions_enabled,
                "clusters": clusters,
            }
        return out

    @app.get("/api/dashboard/activity")
    @consistent
    def dashboard_activity(
        request: Request,
        since: str | None = Query(None, description="UTC date, YYYY-MM-DD"),
        limit: int = Query(
            500, ge=1, le=5000,
            description="Maximum day-rows to return, newest first. `total` and `summary` "
                        "describe the whole set, not this page."),
    ) -> dict:
        """Who used the dashboard, one row per user per UTC day.

        SELF-ONLY by default, and gated by its OWN threshold. This returns identifiable
        personnel data — username, email, the dates somebody was present and the window they
        worked in — and it used to hand all of it to every authenticated user. The dashboard's
        usual justification does not stretch this far: "you could read the groups with oc
        anyway" is true of group membership and false of who looked at it — and unlike every
        other view, Usage lives ONLY in this dashboard's database, reproducible with no `oc`
        command at all.

        THAT IS WHY IT HAS A SECOND, STRICTER TIER (docs/SPEC_usage_admin_tier.md), decided by
        usage_scope rather than viewer_scope. cluster-reader — the auditor persona that keeps
        every wide audit view — must NOT browse colleagues' presence records, and no read check
        separates it from cluster-admin, so the usage threshold asks a write verb. The wide tier
        and the usage tier are independent: a cluster-reader comes out scope=all on /groups and
        scope=self here, same request cycle, same app.

        `userActivity.visibility: all` still restores the old everyone-sees-everyone behaviour
        for a deployment that genuinely wants it — the blunt override, unchanged, and it wins
        over the tier (usage_scope precedence 1).

        Deliberately not a page-view log — see the dashboard_user_activity comment in
        store.py for why this is aggregated rather than per-request.
        """
        # Never from a caller-supplied header. With the proxy disabled the app binds
        # 0.0.0.0 with no authentication, so X-Forwarded-User is whatever was typed, and
        # honouring it here would let anyone read everyone by asserting a name.
        if not settings.oauth_proxy_enabled:
            raise HTTPException(
                status_code=403,
                detail="dashboard usage requires the OAuth proxy; without it there is no "
                       "authenticated identity to scope this to",
            )
        viewer = request.headers.get(USER_HEADER)
        if not viewer:
            raise HTTPException(status_code=403, detail="no authenticated identity")

        # The usage tier, not the wide tier: scope is "all" only via the blunt override or a
        # positive usage-SAR verdict, and everything indeterminate serves the reader's own rows.
        _, scope = usage_scope(request)
        scope_to = None if scope == "all" else viewer
        # The summary is computed over the whole visible set, the rows are one page of it.
        # Without the summary the page counted the rows it was handed and called that the
        # total, which is the same silent-truncation defect the user-bindings endpoint was
        # fixed for: at 1,092 stored rows it showed 167 days and 5,000 interactions against
        # a true 364 and 10,920. `@consistent` because that is now two store calls, and a
        # total from one snapshot beside rows from another can contradict itself.
        summary = store.user_activity_summary(since_day=since, user_name=scope_to)
        rows = store.user_activity(since_day=since, limit=limit, user_name=scope_to)
        return {
            "enabled": activity.enabled,
            "retention_days": settings.user_activity_retention_days,
            "scope": scope,
            "viewer": viewer,
            "total": summary["rows_total"],
            "limit": limit,
            "truncated": len(rows) < summary["rows_total"],
            "summary": {
                "distinct_users": summary["distinct_users"],
                "days": summary["days"],
                "interactions": summary["interactions"],
            },
            "activity": rows,
        }

    def feature_flags() -> dict:
        """Which optional modules this deployment switched on, for the page to show or hide.

        The page reads this ONCE at boot beside `timezone`, exactly as it learns the display
        zone: a fact about the deployment, not about the reader. A module absent from this
        dict on an older build renders nothing — every check on the page is `=== true`.
        Session-shaped modules (the idle timeout) ride /api/whoami's `session` instead,
        because they only exist when there is a session.
        """
        return {"export": settings.ui_export_enabled,
                "reporting": bool(settings.reporting_url), "reporting_prefix": REPORT_PREFIX}

    @app.get("/api/report/ticket")
    def report_ticket(request: Request) -> dict:
        """A short-lived, signed ticket that lets THIS reader call the report service — minted only at the administrator tier.

        The report service holds no cluster credential, so the tier is decided HERE
        (require_admin_tier, the same SubjectAccessReview every gated view uses) and carried to it
        signed: HMAC-SHA256 with the token both pods mount, bound to the proxy's X-Forwarded-User
        and to an expiry. A GET, and deliberately no work: nothing is stored, rendered or fetched —
        the ticket is a pure function of the request, like /api/whoami's tier. 404 when reporting is
        off; 403 with the gate's own sentence below the wide tier.
        """
        if not settings.reporting_url or report_secret is None:
            raise HTTPException(status_code=404, detail="reporting is not enabled on this deployment")
        require_admin_tier(request)
        viewer = trusted_viewer(request)
        if not viewer:
            raise HTTPException(status_code=403, detail="a ticket needs an authenticated viewer, and there is none")
        return {"ticket": mint(report_secret, viewer, TIER_ALL, settings.reporting_ticket_ttl_seconds),
                "expires_in": settings.reporting_ticket_ttl_seconds, "prefix": REPORT_PREFIX, "viewer": viewer}

    @app.get("/api/dashboard/reports")
    @consistent
    def dashboard_reports(
        request: Request,
        limit: int = Query(200, ge=1, le=5000, description="Maximum runs to return, newest first. `total` describes the whole set."),
        offset: int = Query(0, ge=0, description="Page offset."),
    ) -> dict:
        """Who generated which report, when — pulled from the report service by the poller and recorded here.

        USAGE TIER, like /api/dashboard/activity: this is personnel data (a person's use of a
        governance tool) that exists only in the dashboard's own database. `scope` is `all` only for
        the usage tier; everyone else sees their own runs. `enabled` false when reporting is off.
        """
        if not settings.reporting_url:
            return {"enabled": False, "scope": "self", "viewer": trusted_viewer(request), "total": 0, "limit": limit, "truncated": False, "runs": []}
        if not settings.oauth_proxy_enabled:
            raise HTTPException(status_code=403, detail="report usage requires the OAuth proxy; without it there is no authenticated identity to scope this to")
        viewer = request.headers.get(USER_HEADER)
        if not viewer:
            raise HTTPException(status_code=403, detail="no authenticated identity")
        _, scope = usage_scope(request)
        scope_to = None if scope == "all" else viewer
        total = store.count_report_runs(user_name=scope_to)
        rows = store.report_runs(user_name=scope_to, limit=limit, offset=offset)
        return {"enabled": True, "scope": scope, "viewer": viewer, "total": total, "limit": limit,
                "truncated": offset + len(rows) < total, "runs": rows}

    @app.get("/api/version")
    def version() -> dict:
        """What is actually running, provable back to a commit.

        Stamped into the image at build time. `dirty: true` means the build included
        uncommitted changes, so no commit reproduces it — which is the honest answer when
        someone asks "is my fix in there?". `features` names the optional modules switched on
        for this deployment (docs/DESIGN_export.md), so the page renders a control only where
        the operator enabled it.
        """
        commit = os.environ.get("GSD_GIT_COMMIT", "unknown")
        # The timezone the CONTAINER is running in, so the browser can render timestamps in
        # the same zone the logs are stamped with. Without this the page would show UTC
        # beside a log line reading local, and correlating the two becomes arithmetic.
        #
        # The IANA name is what the browser needs (Intl.DateTimeFormat takes `timeZone`);
        # the abbreviation and offset are for labelling, and are resolved HERE because only
        # the server knows whether TZ actually took effect — with no tzdata installed, TZ
        # parses as a POSIX spec and silently means UTC.
        now = datetime.now().astimezone()
        return {
            "leader": elector.is_leader if elector is not None else None,
            "version": os.environ.get("GSD_VERSION", __version__),
            "commit": commit,
            "branch": os.environ.get("GSD_GIT_BRANCH", "unknown"),
            "dirty": commit.endswith("-dirty"),
            "features": feature_flags(),
            "timezone": {
                # None when TZ is unset: the browser then falls back to UTC rather than
                # guessing, because a wrong zone is worse than an explicit one.
                "name": os.environ.get("TZ") or None,
                "abbrev": now.tzname(),
                "utc_offset": now.strftime("%z"),
            },
        }

    @app.get("/readyz")
    def readyz() -> dict:
        """Ready once the store is usable.

        Deliberately not gated on a successful cluster poll: an unreachable cluster is a
        thing this dashboard is meant to *display*, so failing readiness for it would take
        the dashboard down exactly when it has something to report (PLAN §5).
        """
        try:
            store.clusters()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=503, detail=f"store unavailable: {exc}") from exc
        return {"status": "ready", "clusters": len(settings.effective_clusters())}

    # Served from the image, not from a CDN. Falls back to the CDN only when the vendored
    # bundle is absent — a source checkout that has never been through a container build —
    # so `uvicorn gsd.api:create_app` still gives a developer working docs.
    _vendor = os.path.join(STATIC_DIR, "vendor")
    _has_vendor = os.path.isfile(os.path.join(_vendor, "redoc.standalone.js"))
    _JS = "/static/vendor/swagger-ui-bundle.js" if _has_vendor else (
        "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js")
    _CSS = "/static/vendor/swagger-ui.css" if _has_vendor else (
        "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css")
    _REDOC = "/static/vendor/redoc.standalone.js" if _has_vendor else (
        "https://cdn.jsdelivr.net/npm/redoc@2/bundles/redoc.standalone.js")
    if not _has_vendor:
        log.warning(
            "API docs will load from a CDN: no vendored bundle at %s. In a disconnected "
            "cluster /api and /api/redoc will render blank. This is expected for a source "
            "checkout and never for a built image.", _vendor,
        )

    @app.get("/api", include_in_schema=False)
    def swagger_ui() -> HTMLResponse:
        """Swagger UI, rendered from assets shipped in this image."""
        return get_swagger_ui_html(
            openapi_url="/api/openapi.json",
            title=f"{TITLE} — API",
            swagger_js_url=_JS,
            swagger_css_url=_CSS,
            # The default favicon is fetched from fastapi.tiangolo.com; the app already
            # serves its own, and one fewer third party sees an authenticated admin's tab.
            swagger_favicon_url="/static/favicon.svg",
        )

    @app.get("/api/redoc", include_in_schema=False)
    def redoc_ui() -> HTMLResponse:
        """ReDoc, rendered from assets shipped in this image."""
        return get_redoc_html(
            openapi_url="/api/openapi.json",
            title=f"{TITLE} — API reference",
            redoc_js_url=_REDOC,
            redoc_favicon_url="/static/favicon.svg",
        )

    @app.get("/api/docs", include_in_schema=False)
    def api_docs_alias() -> RedirectResponse:
        """`/api/docs` is the path people type; `/api` is where the UI is mounted.

        A redirect rather than a second mount, so there is one canonical URL to bookmark,
        one to link from the README, and no chance of the two rendering different schemas
        after a FastAPI upgrade.
        """
        return RedirectResponse(url="/api", status_code=308)

    # Rendered pages, keyed by filename: (digest of the source bytes, name they were rendered
    # with, rendered body, ETag). The source is read and hashed on every request — 180 KB from
    # the page cache, well under a millisecond — because a key built from mtime alone answered
    # 304 with a stale tag after a content swap that kept the mtime (cp -p, a bind mount; the
    # Cursor pass found it). Only the substitution is cached, and the key is the content itself.
    rendered_pages: dict[str, tuple[str, str, bytes, str]] = {}

    def named_page(filename: str, request: Request) -> Response:
        """A static page with the dashboard's name substituted in.

        The two HTML files carry __GSD_TITLE__ where the name goes, and the name itself is
        gsd.TITLE — one place, read here, so the tab title, the header, the signed-out page
        and the API docs cannot disagree. Escaped, because a name is text and not markup.

        With no Cache-Control, browsers apply heuristic caching to HTML and keep serving
        the old page after a redeploy — the user sees a version that no longer exists and
        reasonably concludes the change was never shipped. The whole app is one file, so it
        must always be revalidated; there is nothing here worth caching and a stale shell
        silently disables every fix behind it.

        REVALIDATION NEEDS A VALIDATOR. `no-cache` lets the browser keep a copy but forbids
        reusing it unchecked, and the check is only cheap when the response carries something
        to check against: MDN's pattern for always-fresh HTML is exactly no-cache plus ETag and
        Last-Modified, answered with a bodiless 304. The FileResponse this replaced sent both
        validators but never answered a conditional request (Starlette leaves 304s to
        StaticFiles), so every reload paid for the whole file; the first version of this
        substitution dropped the validators as well, which the review measured. Now: a strong
        ETag over the RENDERED body, so it moves with the file or the name; Last-Modified from
        the file; If-None-Match compared the way RFC 9110 §13.1.2 requires (weak comparison,
        over a comma-separated list). The 304 is built the way §15.4.5 requires: it MUST carry
        Cache-Control and ETag because the 200 would have (Date comes from uvicorn), MUST NOT
        carry a body, and SHOULD NOT carry other representation metadata — so Last-Modified
        rides the 200 only; with an ETag present it guides no cache update on a 304. Not
        Jinja2Templates: FastAPI's documented engine would be one more dependency for one text
        node, and it sets none of these headers.
        """
        path = os.path.join(STATIC_DIR, filename)
        with open(path, "rb") as fh:
            source = fh.read()
        mtime = os.stat(path).st_mtime
        digest = hashlib.sha256(source).hexdigest()
        cached = rendered_pages.get(filename)
        if cached is None or cached[0] != digest or cached[1] != TITLE:
            body = source.decode("utf-8").replace("__GSD_TITLE__", html.escape(TITLE)).encode("utf-8")
            etag = '"' + hashlib.sha256(body).hexdigest()[:32] + '"'
            cached = (digest, TITLE, body, etag)
            # Two threads can render at once (sync handlers run on a pool). Either result is a
            # correct render of the bytes that thread read, and the key is those bytes, so the
            # last writer wins harmlessly; the next request re-reads and re-keys regardless.
            rendered_pages[filename] = cached
        _, _, body, etag = cached
        headers = {"Cache-Control": "no-cache, must-revalidate", "ETag": etag}
        if_none_match = request.headers.get("if-none-match")
        if if_none_match is not None:
            offered = [tag.strip().removeprefix("W/") for tag in if_none_match.split(",")]
            unchanged = etag in offered or "*" in offered
        else:
            # Only consulted when there is no entity tag to compare — §13.1.3. An HTTP-date is
            # always GMT (§5.6.7): a value that parses without a zone is not one, and treating
            # it as local time would answer 304 for a date the client never meant.
            unchanged = False
            since = request.headers.get("if-modified-since")
            if since is not None:
                try:
                    parsed = parsedate_to_datetime(since)
                except (TypeError, ValueError):
                    parsed = None
                if parsed is not None and parsed.tzinfo is not None:
                    unchanged = int(mtime) <= parsed.timestamp()
        if unchanged:
            return Response(status_code=304, headers=headers)
        headers["Last-Modified"] = formatdate(mtime, usegmt=True)
        return HTMLResponse(body, headers=headers)

    @app.get("/")
    def index(request: Request) -> Response:
        return named_page("index.html", request)

    @app.get("/signed-out")
    def signed_out(request: Request) -> Response:
        # The proxy's -logout-url target, listed in oauthProxy.skipAuthRegex. It renders at
        # the exact moment the session cookie has just been cleared, so it reads no headers
        # and claims nothing about who signed out — anything it said would be
        # caller-supplied. Same Cache-Control reasoning as named_page(): a stale cached copy
        # after a redeploy would misdescribe what logout actually does, and what it does
        # NOT do (end the reader's other cluster sessions) is its entire purpose.
        return named_page("signed-out.html", request)

    # The /static mount below serves the whole directory, these two source files included, and
    # a raw copy carries the placeholder where the name should be — measured by the review as a
    # 200 at /static/index.html with __GSD_TITLE__ in it. Routes are matched in registration
    # order, so these two, declared before the mount, shadow the raw files with the rendered
    # pages. Moving the files out of the directory would be cleaner, but a dozen tests and
    # doc anchors name gsd/static/index.html. The mount itself refuses the sources too, below:
    # exact routes do not catch /static/index.html/ or /static//index.html, which StaticFiles
    # normalises to the same file, nor a case variant on a case-insensitive volume (measured:
    # all three served the raw token on macOS).
    # Out of the schema like the docs-UI routes: they are the page, not the API.
    @app.get("/static/index.html", include_in_schema=False)
    def index_raw(request: Request) -> Response:
        return named_page("index.html", request)

    @app.get("/static/signed-out.html", include_in_schema=False)
    def signed_out_raw(request: Request) -> Response:
        return named_page("signed-out.html", request)

    if os.path.isdir(STATIC_DIR):
        app.mount("/static", PageSourceRefusingStaticFiles(directory=STATIC_DIR), name="static")

    app.state.store = store
    app.state.signals = signals
    app.state.settings = settings
    # The visibility seam, published for the handlers and for tests to substitute: a fake
    # resolver here (any object with resolve(viewer) -> "all" | "self") is how a test
    # forces the all tier, the self tier, or an indeterminate answer without a cluster.
    # None whenever the decision was injected into build_app instead — viewer_scope then
    # falls back to that injected callable.
    app.state.tier_resolver = resolver
    # The Usage tab's OWN seam, deliberately a distinct attribute and a distinct resolver
    # instance: usage_scope reads only this one, so a test (and the live app) can hold a
    # cluster-reader at scope=all on the wide tier and scope=self on Usage in the same request.
    app.state.usage_tier_resolver = usage_resolver
    # The two cluster-configuration levels, on their own seams so a test can substitute either
    # without touching the other or the wide tier (#230).
    app.state.clusterconfig_view_resolver = clusterconfig_view_tier or clusterconfig_view_resolver
    app.state.clusterconfig_manage_resolver = clusterconfig_manage_tier or clusterconfig_manage_resolver
    # One resolver per remote-sar cluster, keyed by cluster id — the per-cluster seam. A test
    # installs `{"prod-east": stub}` here to decide a remote without a cluster; a remote with
    # no entry is never wide.
    app.state.remote_tier_resolvers = remote_resolvers
    return app


def create_app() -> FastAPI:
    """Entrypoint for `uvicorn gsd.api:create_app --factory`."""
    # The offset (%z) is not decoration. TZ is settable on the container, so a log line
    # reading "21:17:59" is UTC on one deployment and local on another, and nothing in the
    # line says which — the same ambiguity the dashboard header had between its own clock
    # and the UTC timestamps beneath it. Correlating a log against a stored timestamp (all
    # of which end in Z) needs the offset present, not inferred from a deployment's values.
    level, complaint = _resolve_log_level(os.environ.get("GSD_LOG_LEVEL"))
    logging.basicConfig(
        level=level,
        format="%(asctime)s%(tzoffset)s %(levelname)-7s %(name)s %(message)s",
    )
    # %z is not a logging format code; it belongs to strftime, and asctime is built with a
    # fixed default format. Injecting it as a record attribute is the documented way to get
    # the offset into every line without replacing the formatter wholesale.
    tzoffset = time.strftime("%z")
    old_factory = logging.getLogRecordFactory()

    def _factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        record.tzoffset = tzoffset
        return record

    logging.setLogRecordFactory(_factory)
    if complaint:
        # Emitted AFTER basicConfig, or it would be the call that configures logging and the
        # format above would never apply. At WARNING it is visible at the default level, which is
        # the point: the reader asked for a level they did not get.
        log.warning("%s", complaint)
    _quiet_transport_framing()
    for grumble in _apply_http_log_level() + _apply_per_logger_levels():
        log.warning("%s", grumble)
    return build_app(load_settings(os.environ.get("GSD_CONFIG", "clusters.yaml")))


#: The five this app accepts, in ascending order, and the only five it advertises. Python itself
#: would take a few more spellings; they are refused on purpose, because a level is a promise about
#: what you will see and two ways to write one level is not one promise. The chart refuses the same
#: set at render time; this is the second boundary, for a container configured directly.
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def _resolve_log_level(raw: str | None) -> tuple[int, str | None]:
    """One GSD_LOG_LEVEL value to a logging level, never raising. Returns (level, complaint).

    WHY THIS EXISTS RATHER THAN PASSING THE STRING STRAIGHT THROUGH. `logging.basicConfig` raises
    `ValueError: Unknown level: 'debug'` for anything it does not recognise, and this function is
    the uvicorn factory — so the container did not start. Measured: lowercase `debug`, `Debug`,
    `info`, a numeric `20`, and an empty string each crash-loop the pod, and lowercase is the
    natural thing to type. Crashing a whole dashboard over the spelling of a log level is
    disproportionate; a log level is not a security control, so this degrades and says so.

    CASE IS NORMALISED because `debug` unambiguously means DEBUG. A value that is not a level at
    all falls back to INFO and complains — the complaint is returned rather than logged here
    because logging is not configured yet at the moment this runs.

    THE COMPLAINT POINTS AT `authLogLevel`, because the commonest reason to be fiddling with a log
    level on this deployment is to make the Logins tab show something — and that is a different
    setting, on a different object, which raises the OAUTH-SERVER's verbosity rather than this
    app's. Naming it turns a puzzling fallback into a one-line fix. Only the five levels this app
    accepts are ever listed; the message does not catalogue values that do not work here.
    """
    if raw is None or not raw.strip():
        return logging.INFO, None
    wanted = raw.strip().upper()
    if wanted in LOG_LEVELS:
        return getattr(logging, wanted), None

    # THE REJECTED VALUE IS NOT ECHOED, and that is a deliberate reversal of the obvious design.
    # Repeating it back is the friendlier message and the wrong one: an environment variable is a
    # place credentials get miswired, and this ran early enough to copy whatever it found straight
    # into an admin-readable pod log. Measured on the first version — a value of
    # `sha256~…-secret-token-value` came back verbatim in the warning, and a one-million-character
    # value produced a 1,000,369-character log record. A typo became a disclosure and a log-pipeline
    # problem at once. The accepted set is enough to repair the setting; the operator can read their
    # own values file.
    #
    # ONE POINTER, NO CATALOGUE. The message names the five levels that work and the ONE other
    # setting somebody is likely to have been reaching for; it does not enumerate the values that do
    # not work here. Listing them reads as a menu of near-misses, and a rejected value is not worth
    # advertising — the accepted set plus the likely mistake is the whole of what repairs the
    # setting.
    return logging.INFO, (
        f"GSD_LOG_LEVEL is set to a {len(raw)}-character value that is not a log level this app "
        f"accepts, so it is running at INFO. The value is deliberately not repeated here, in case "
        f"something other than a log level was wired into it. Use one of "
        f"{', '.join(LOG_LEVELS)} (case does not matter). If you were trying to raise the "
        f"oauth-server's verbosity so the Logins tab has something to read, that is the chart's "
        f"authLogLevel value — a different setting, on a different object, not this one."
    )


def _quiet_transport_framing() -> None:
    """Keep DEBUG meaning "this app's reasoning" rather than "somebody's TCP handshake".

    MEASURED IN THE LIVE POD at GSD_LOG_LEVEL=DEBUG: 428 lines, 366 of them DEBUG, attributed
    `httpcore.http11` 260, `httpcore.connection` 96, `gsd.poller` 6, `gsd.kube` 4. So 97% of what
    DEBUG produced was transport framing — `connect_tcp.started`, `send_request_headers.complete`
    — and the ten lines an operator turned it on for were buried in it. A level that floods is a
    level nobody turns on twice.

    HTTPX WAS DELIBERATELY LEFT ALONE HERE, AND NOW HAS ITS OWN VARIABLE (#245). The original
    reasoning stands on its own terms: `HTTP Request: GET <url> "200 OK"` is SEMANTIC — which API
    call, against which cluster, with what status — and at ONE cluster it cost 12 lines a cycle
    against httpcore's 356, so thresholding it would have been over-reach. What changed is the
    fleet, not the argument. MEASURED ON THE LAB AT FOUR CLUSTERS, 60s refresh: 1 784 lines in 90
    minutes, 1 082 of them httpx request URLs — 61%, and ~10 000 an hour at the forty clusters the
    cluster-configuration module exists to serve. The decision was outgrown rather than wrong.

    It is also a PROXY for the facts we actually want. Once `gsd.clusterconfig` logs which cluster,
    which phase and what outcome (see `clusterconfig/events.py`), a list of URLs is the same story
    told worse. So httpx moves to `GSD_HTTP_LOG_LEVEL` (default WARNING, `INFO` restores exactly
    today's behaviour) rather than being pinned here — the capability is a variable away, and the
    line an operator misses most was never the URL.

    `httpcore` is the layer below: the same requests, spelled as socket events.

    NOT disabled, THRESHOLDED. A TLS handshake failing against a corporate CA bundle is a real
    thing to have to diagnose, and it is invisible above WARNING. `GSD_DEBUG_HTTP=true` restores
    the framing for exactly that, so the capability is one variable away instead of gone.

    Set on the logger rather than by filtering the root handler, because these records should not
    be created at all: `httpcore` emits them at DEBUG, and a logger whose level rejects them never
    formats the message.
    """
    if os.environ.get("GSD_DEBUG_HTTP", "").strip().lower() in {"1", "true", "yes"}:
        return
    logging.getLogger("httpcore").setLevel(logging.WARNING)


#: The loggers `GSD_HTTP_LOG_LEVEL` governs: the per-request record, inbound and outbound.
#: `uvicorn.access` is here because its access lines are the same kind of thing as httpx's — one
#: line per request, useful when you are asking about requests and noise when you are not. It was
#: previously unreachable by any setting at all: its logger carries propagate=False and its own
#: handler, so `GSD_LOG_LEVEL` could neither raise nor lower it, and `/readyz` and `/metrics` wrote
#: a line apiece forever. Naming it here is the first time an operator can turn it down.
HTTP_LOGGERS = ("httpx", "uvicorn.access")


def _apply_http_log_level() -> list[str]:
    """`GSD_HTTP_LOG_LEVEL` — the per-request record, separately from this app's own reasoning.

    WHY SEPARATE RATHER THAN FOLDED INTO GSD_LOG_LEVEL. They answer different questions. "What is
    the dashboard doing about cluster ocp-east?" is `gsd.*`; "what HTTP calls went out?" is httpx.
    Tying them means an operator who wants the first at DEBUG gets a flood of the second, which is
    exactly the state #245 measured: 61% of the pod's lines were request URLs, and our own module's
    lines were the ones being hidden.

    DEFAULT WARNING, not OFF. A request that fails is still worth a line; the routine 200s are not.
    `GSD_HTTP_LOG_LEVEL=INFO` restores the previous behaviour exactly, for whoever wants the full
    request record back — which is why the old behaviour is a value rather than a deleted feature.

    Returns complaints rather than logging them, for the same reason `_resolve_log_level` does: this
    can run before the caller has decided what to do with them.
    """
    raw = os.environ.get("GSD_HTTP_LOG_LEVEL")
    complaints: list[str] = []
    if raw is None or not raw.strip():
        level = logging.WARNING
    else:
        wanted = raw.strip().upper()
        if wanted in LOG_LEVELS:
            level = getattr(logging, wanted)
        else:
            level = logging.WARNING
            # The value is not echoed, for the reason `_resolve_log_level` states at length: an
            # environment variable is a place credentials get miswired.
            complaints.append(
                f"GSD_HTTP_LOG_LEVEL is set to a {len(raw)}-character value that is not a log "
                f"level this app accepts, so the HTTP request record is at WARNING. Use one of "
                f"{', '.join(LOG_LEVELS)} (case does not matter); INFO restores the per-request "
                f"lines. This setting governs {', '.join(HTTP_LOGGERS)} only — this app's own "
                f"loggers are GSD_LOG_LEVEL."
            )
    for name in HTTP_LOGGERS:
        logging.getLogger(name).setLevel(level)
    return complaints


def _apply_per_logger_levels() -> list[str]:
    """`GSD_LOG_LEVELS=gsd.clusterconfig=DEBUG,httpx=INFO` — raise one concern, not the fleet.

    THE PROBLEM IT SOLVES. Diagnosing one cluster's connection meant `GSD_LOG_LEVEL=DEBUG`, which
    turns on every module's reasoning at once across however many clusters are polling. The thing
    you wanted was one logger. With forty clusters that difference is the difference between a
    readable log and a flood.

    LAST ONE WINS for a repeated logger, and an unparseable pair is skipped with a complaint rather
    than failing the parse — the same degrade-and-say-so contract as every other log setting here.

    THE NAME IS NOT ECHOED EITHER (review of #247, Grok C4). The first version reported it, arguing
    that a logger name is structurally public because it names a module. That argument assumes the
    value IS a logger name — which is exactly the assumption that fails when something else has been
    miswired into the variable, and "an environment variable is a place credentials get miswired" is
    the whole reason `_resolve_log_level` refuses to repeat its own. The length and the accepted set
    are enough to repair the setting; the operator can read their own values file.

    A LEVEL SET HERE OVERRIDES THE ROOT LEVEL, in both directions: `Logger.isEnabledFor` consults the
    logger's own level, and `callHandlers` walks ancestors' handlers without re-checking ancestors'
    levels. So `gsd.clusterconfig=DEBUG` emits even at `GSD_LOG_LEVEL=ERROR`, which is the point —
    and `gsd.poller=ERROR` silences that module even at `GSD_LOG_LEVEL=DEBUG`, which is the trap.
    The root logger itself is refused here (`root=…` is skipped with a complaint): it is every
    logger at once, and its level is GSD_LOG_LEVEL's.
    """
    raw = os.environ.get("GSD_LOG_LEVELS")
    if raw is None or not raw.strip():
        return []
    complaints: list[str] = []
    for pair in raw.split(","):
        if not pair.strip():
            continue
        name, sep, value = pair.partition("=")
        name, value = name.strip(), value.strip().upper()
        if not sep or not name:
            complaints.append(
                f"GSD_LOG_LEVELS has an entry that is not name=LEVEL, so it was skipped. The "
                f"format is a comma-separated list, e.g. gsd.clusterconfig=DEBUG,httpx=INFO."
            )
            continue
        if logging.getLogger(name) is logging.getLogger():
            # `root=CRITICAL` would silence every logger at once — `logging.getLogger("root")` IS
            # the root logger — with no complaint and no line saying so (review of #247, OB3 C4).
            # The root's level is GSD_LOG_LEVEL's job, and one setting per level is the contract.
            complaints.append(
                "GSD_LOG_LEVELS names the root logger, which is skipped: that would set every "
                "logger at once and override GSD_LOG_LEVEL silently. Set GSD_LOG_LEVEL instead."
            )
            continue
        if value not in LOG_LEVELS:
            complaints.append(
                f"GSD_LOG_LEVELS has a {len(name)}-character logger name set to a value that is "
                f"not a log level this app accepts, so that logger is unchanged. Neither the name "
                f"nor the value is repeated here, in case something other than a log setting was "
                f"wired into it. Use one of {', '.join(LOG_LEVELS)}."
            )
            continue
        logging.getLogger(name).setLevel(getattr(logging, value))
    return complaints
