"""Read-only HTTP API (PLAN §11).

No endpoint returns a token or accepts one from the browser. The frontend talks only to this
service and never holds a cluster credential (PLAN §9).
"""

from __future__ import annotations

import functools
import logging
import os
import re
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from . import __version__
from . import state as st
from .activity import EMAIL_HEADER, INTERACTION_HEADER, USER_HEADER, ActivityRecorder
from .config import Settings, load_settings
from .kube import TierResolver
from .leader import LeaderElector
from .metrics import RuntimeSignals, build_registry
from .poller import Poller
from .storage import StorageBackend, open_backend
from . import loginlog

log = logging.getLogger(__name__)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

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
#   * `empty_group`, `unattributed`, `stale_group` name groups from the self-scoped Groups
#     tab (and an empty group can never contain the viewer);
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
    poller = Poller(store, settings, elector, signals=signals)
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

    def viewer_scope(request: Request) -> tuple[str | None, str]:
        """Resolve this request to (viewer, scope). The failure direction IS the control.

        `scope` is "all" only when restrictions are off, or when the tier resolver
        POSITIVELY answers "all" for this viewer. Everything else — no viewer, no
        resolver wired, a resolver error or timeout, an unrecognised answer — lands on
        "self", never on the wide view (requirements §5.4, decision D1).
        """
        viewer = trusted_viewer(request)
        if not restrict:
            return viewer, "all"
        # Read off app.state PER REQUEST — the published seam (see app.state.tier_resolver
        # below), so a test-substituted resolver is honoured by every handler. The
        # build-time `tier_resolver` callable is the fallback for an app built with an
        # injected decision and nothing published.
        state_resolver = getattr(app.state, "tier_resolver", None)
        if not viewer or (state_resolver is None and tier_resolver is None):
            # Counted like every decision below; only the restrictions-off return above is
            # not a decision. gsd_visibility_decisions_total is what makes the served
            # all:self mix visible — the everyone-silently-narrowed signature.
            signals.note_decision("admin", "self")
            return viewer, "self"
        try:
            tier = (state_resolver.resolve(viewer) if state_resolver is not None
                    else tier_resolver(viewer))
        except Exception:  # noqa: BLE001
            # Logged with the trace, served as self: an API-server blip degrades the VIEW,
            # never the availability — the reader sees their own data, not an error page.
            log.exception("tier resolution failed for %r; serving the self view", viewer)
            signals.note_decision("admin", "self")
            return viewer, "self"
        # Only the exact string "all" widens — the _visibility_setting discipline applied
        # to the resolver's answer, so a buggy resolver cannot widen by returning junk.
        scope = "all" if tier == "all" else "self"
        signals.note_decision("admin", scope)
        return viewer, scope

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
        if settings.user_activity_visibility == "all":
            # A served wide decision, counted as one: a deployment that set the blunt
            # override should see that fact on the graph rather than a mysterious all-tier.
            signals.note_decision("usage", "all")
            return viewer, "all"
        # Restrictions off (or proxy off) runs no tier machinery — but Usage is NOT the wide
        # view, so it stays self here rather than widening. This mirrors the pre-tier behaviour,
        # where /api/dashboard/activity was governed by userActivity.visibility alone and never
        # by the visibility tier: turning cluster-data restrictions off must not, as a side
        # effect, expose colleagues' presence records.
        if not restrict:
            return viewer, "self"
        state_resolver = getattr(app.state, "usage_tier_resolver", None)
        if not viewer or (state_resolver is None and usage_tier_resolver is None):
            signals.note_decision("usage", "self")
            return viewer, "self"
        try:
            tier = (state_resolver.resolve(viewer) if state_resolver is not None
                    else usage_tier_resolver(viewer))
        except Exception:  # noqa: BLE001
            # An API-server blip degrades the Usage VIEW to the reader's own rows, never the
            # availability and never the wide set — the same discipline viewer_scope follows.
            log.exception("usage tier resolution failed for %r; serving the self view", viewer)
            signals.note_decision("usage", "self")
            return viewer, "self"
        scope = "all" if tier == "all" else "self"
        signals.note_decision("usage", scope)
        return viewer, scope

    def require_viewer(viewer: str | None) -> str:
        """Self-scoped data needs a name to scope to; without one it is refused.

        The /api/dashboard/activity rule: when no proxy fronts the app (or the proxy sent
        no identity header), X-Forwarded-User is whatever the caller typed, and honouring
        it would let anyone read anyone by asserting a name.
        """
        if not viewer:
            raise HTTPException(
                status_code=403,
                detail="this data is scoped to the authenticated viewer, and there is no "
                       "authenticated identity to scope it to",
            )
        return viewer

    def require_admin_tier(request: Request) -> str:
        """The administrator tier, or a refusal that names itself as one.

        For the views that are ABOUT THE CLUSTER rather than about the reader: its whole RBAC
        binding surface, the operator's configuration, the sync CRs. These cannot be scoped
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
        surface, and never a reader's own. `docs/ACCESS_CONTROL.md` tabulates both.

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
        _, scope = viewer_scope(request)
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
            for cluster in settings.clusters:
                store.upsert_cluster(cluster.name, cluster.api_url, cluster.enabled)
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
        title="GroupSync dashboard",
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

    def require_cluster(cluster_id: str):
        cluster = settings.cluster(cluster_id)
        if cluster is None:
            raise HTTPException(status_code=404, detail=f"unknown cluster {cluster_id!r}")
        return cluster

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
        counts = {"dangling": 0, "unresolved": 0, "built_in": 0}
        for finding in store.binding_findings(cluster_id):
            counts[finding["finding"]] = counts.get(finding["finding"], 0) + 1
        return {
            "dangling_bindings": counts["dangling"],
            "unresolved_bindings": counts["unresolved"],
            "builtin_bindings": counts["built_in"],
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
        _, scope = viewer_scope(request)
        out = []
        for row in store.clusters():
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
        _, scope = viewer_scope(request)
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
        viewer, scope = viewer_scope(request)
        rows = store.groups(
            cluster_id, state,
            user_name=None if scope == "all" else require_viewer(viewer),
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
        viewer, scope = viewer_scope(request)
        if scope == "self" and not store.is_group_member(
            cluster_id, name, require_viewer(viewer)
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
            # DIRECT bindings only. Role rules are never fetched or expanded, so this is
            # not an effective-permission calculation and must not be presented as one.
            "bindings": store.group_bindings(cluster_id, name),
        }

    @app.get("/api/clusters/{cluster_id}/users")
    def list_users(
        request: Request,
        cluster_id: str,
        limit: int = Query(
            default=1000, ge=1, le=10000,
            description="Maximum users to return. `truncated` says whether more exist."),
    ) -> dict:
        """Users with a membership, bounded and honest about it.

        This used to return a bare unbounded list — 102,921 bytes at reference scale, and
        it grows with the size of the directory rather than with anything the dashboard
        controls. The response is now an object so `truncated` can be reported: a clipped
        list that looks like a complete one is the failure worth avoiding.

        SELF-SCOPED under view restrictions: a plain reader gets their own row or an
        empty list, because `list users.user.openshift.io` is a permission they do not
        hold — the only self-read OpenShift grants everyone is `get users/~`.
        """
        require_cluster(cluster_id)
        viewer, scope = viewer_scope(request)
        rows = store.users(
            cluster_id, limit=limit,
            user_name=None if scope == "all" else require_viewer(viewer),
        )
        truncated = len(rows) > limit
        return {
            "cluster": cluster_id,
            "scope": scope,
            "viewer": viewer,
            "count": min(len(rows), limit),
            "truncated": truncated,
            "limit": limit,
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
        viewer, scope = viewer_scope(request)
        if scope == "self" and name != require_viewer(viewer):
            raise HTTPException(
                status_code=403,
                detail="user profiles other than your own need the wide tier",
            )
        groups = store.user_groups(cluster_id, name)
        changes = store.membership_events(cluster_id, user_name=name, limit=100)
        # A user with no CURRENT groups is not unknown — they may have just been removed
        # from the last one, and "they are in nothing now" is the answer to the question,
        # not an error. 404 only when we have never seen them at all.
        if not groups and not changes:
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
            "groups": groups,
            "changes": changes,
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
        limit: int = Query(
            default=200, ge=1, le=2000,
            description="Maximum attempts returned, newest first. `truncated` says whether older "
                        "ones were dropped; `total` and `summary` always describe the whole "
                        "retained record, never this page."),
    ) -> dict:
        """Login attempts against this cluster's oauth-server: who, when, and why it failed.

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
        viewer, scope = viewer_scope(request)
        if scope == "self":
            me = require_viewer(viewer)
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
        rows = store.login_events(cluster_id, user_name=user, outcome=outcome, limit=limit + 1)
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
            "note": "read from the oauth-server log at Debug verbosity; covers only the period "
                    "since capture began — earlier logins were never recorded and cannot be "
                    "fetched, and rows older than the configured retention age out",
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
        viewer, scope = viewer_scope(request)
        access = store.cluster_access_group(cluster_id)
        if scope == "self":
            # THE VIEWER'S OWN GATE STATUS and nothing about anyone else. The DN, the
            # discovery source and both people-lists are withheld — the lists are other
            # people's findings, and the DN maps the directory. Withheld values are None,
            # never fabricated zeros: a summary of zeros would read as "no findings" to a
            # reader who cannot know it was narrowed. `in_access_group` is None when no
            # synced gate group exists to compare against — "we cannot tell" is a
            # different statement from "not a member", same contract as the logins rows.
            me = require_viewer(viewer)
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
        """
        require_cluster(cluster_id)
        require_admin_tier(request)
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
        rows = store.all_bindings(cluster_id, limit=limit, offset=offset)
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
        viewer, scope = viewer_scope(request)
        me = None if scope == "all" else require_viewer(viewer)
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
        require_admin_tier(request)
        return {
            "cluster": cluster_id,
            "scope": "all",
            "viewer": trusted_viewer(request),
            **store.operator_configs(cluster_id),
        }

    @app.get("/api/clusters/{cluster_id}/membership-changes")
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
        viewer, scope = viewer_scope(request)
        # limit + 1, as in list_events — see docs/api-contract.md R3. This log previously
        # cut off at 100 with nothing saying so, which on an audit trail reads as "no
        # further changes" rather than "not shown".
        rows = store.membership_events(
            cluster_id,
            user_name=None if scope == "all" else require_viewer(viewer),
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
        viewer, scope = viewer_scope(request)
        now = datetime.now(UTC)
        alerts: list[dict] = []
        for row in store.clusters():
            cluster_id = row["id"]
            if row["status"] and row["status"] != "ok":
                alerts.append(
                    {
                        "cluster": cluster_id,
                        "kind": row["status"],
                        "subject": cluster_id,
                        "detail": row["message"] or "cluster poll failed",
                        "severity": "critical",
                    }
                )
                # A degraded cluster's cached rows are stale by definition; computing
                # group-level alerts from them would report yesterday's state as today's.
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
            )
            alerts.extend(a.as_dict() for a in computed)

            # Only the `dangling` tier alerts. `built_in` is normal, and `unresolved`
            # cannot be distinguished from a group that simply has not synced yet, so
            # alerting on either would produce noise that trains people to ignore this.
            for row in store.binding_findings(cluster_id):
                if row["finding"] != "dangling":
                    continue
                # `where`, not `scope`: this handler's `scope` is the visibility tier, and
                # a loop-local rebinding here once disabled the self filter below — the
                # feed failed OPEN on exactly the clusters that had a dangling finding.
                where = (
                    f"namespace {row['binding_namespace']}"
                    if row["binding_namespace"]
                    else "cluster-wide"
                )
                alerts.append(
                    {
                        "cluster": cluster_id,
                        "kind": "dangling_binding",
                        "subject": row["binding_name"],
                        "detail": (
                            f"{row['binding_kind']} grants {row['role_name']} {where} to "
                            f"group {row['group_name']!r}, which the operator used to "
                            f"manage and no longer exists — this binding now grants nobody"
                        ),
                        "severity": "critical",
                    }
                )
        if scope == "self":
            alerts = _alerts_for_self(alerts)
        severity_rank = {"critical": 0, "warning": 1}
        alerts.sort(key=lambda a: (severity_rank.get(a["severity"], 9), a["cluster"], a["kind"]))
        return {
            "scope": scope,
            "viewer": viewer,
            "count": len(alerts),
            "alerts": alerts,
        }

    metrics_registry = build_registry(store, grace, elector,
                                      signals=signals, settings=settings)

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

        `session` carries the CONFIGURED durations, never a deadline. The session cookie is
        HttpOnly and the proxy forwards no session-age header, so the true expiry is not
        observable from here; these numbers are trustworthy only because the ConfigMap
        renders them from the same chart values as the proxy's own flags. The browser owns
        the countdown model built on them — see static/index.html.

        NEVER POLL THIS ON A TIMER. Requesting it through the proxy re-stamps the session
        cookie like any other request, so a page calling it periodically would hold every
        session open forever — the exact defect the durations exist to fix. It is called
        once, at page load; the page's "Stay signed in" control re-proves the session with
        an ordinary interaction-marked data refresh instead of calling this again.
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
                }
                if authenticated
                else None
            ),
        }
        if authenticated:
            # The tier from the SAME decision path the data handlers use — viewer_scope
            # reads the app.state seam per request and never raises — so the pill can
            # never disagree with the pages it sits above. An indeterminate tier is SELF.
            _, scope = viewer_scope(request)
            out["visibility"] = {"scope": scope, "enabled": settings.view_restrictions_enabled}
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

    @app.get("/api/version")
    def version() -> dict:
        """What is actually running, provable back to a commit.

        Stamped into the image at build time. `dirty: true` means the build included
        uncommitted changes, so no commit reproduces it — which is the honest answer when
        someone asks "is my fix in there?".
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
        return {"status": "ready", "clusters": len(settings.clusters)}

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
            title="GroupSync dashboard — API",
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
            title="GroupSync dashboard — API reference",
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

    @app.get("/")
    def index() -> FileResponse:
        # With no Cache-Control, browsers apply heuristic caching to HTML and keep serving
        # the old page after a redeploy — the user sees a version that no longer exists and
        # reasonably concludes the change was never shipped. The whole app is this one
        # file, so it must always be revalidated; there is nothing here worth caching and a
        # stale shell silently disables every fix behind it.
        return FileResponse(
            os.path.join(STATIC_DIR, "index.html"),
            headers={"Cache-Control": "no-cache, must-revalidate"},
        )

    @app.get("/signed-out")
    def signed_out() -> FileResponse:
        # The proxy's -logout-url target, listed in oauthProxy.skipAuthRegex. It renders at
        # the exact moment the session cookie has just been cleared, so it reads no headers
        # and claims nothing about who signed out — anything it said would be
        # caller-supplied. Same Cache-Control reasoning as index(): a stale cached copy
        # after a redeploy would misdescribe what logout actually does, and what it does
        # NOT do (end the reader's other cluster sessions) is its entire purpose.
        return FileResponse(
            os.path.join(STATIC_DIR, "signed-out.html"),
            headers={"Cache-Control": "no-cache, must-revalidate"},
        )

    if os.path.isdir(STATIC_DIR):
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    app.state.store = store
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

    HTTPX IS DELIBERATELY LEFT ALONE. Its `HTTP Request: GET <url> "200 OK"` lines are SEMANTIC —
    which API call, against which cluster, with what status — and they are the record of what the
    poller actually asked for. They sit at INFO by httpx's own choice, the chart README documents
    them as intentionally present at the default, and they cost 12 lines a cycle rather than 356.
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
