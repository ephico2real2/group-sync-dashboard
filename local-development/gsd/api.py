"""Read-only HTTP API (PLAN §11).

No endpoint returns a token or accepts one from the browser. The frontend talks only to this
service and never holds a cluster credential (PLAN §9).
"""

from __future__ import annotations

import functools
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from . import __version__
from . import kube
from . import state as st
from .activity import EMAIL_HEADER, INTERACTION_HEADER, USER_HEADER, ActivityRecorder
from .config import Settings, load_settings
from .leader import LeaderElector
from .metrics import build_registry
from .poller import Poller
from .storage import StorageBackend, open_backend
from . import loginlog

log = logging.getLogger(__name__)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

# Mirrors oauthProxy.skipAuthRegex. Requests here reach the app WITHOUT authentication, so
# nothing they claim about identity can be believed or recorded.
# Mirrors oauthProxy.skipAuthRegex. Requests here reach the app WITHOUT authentication, so
# nothing they claim about identity can be believed or recorded. /signed-out is the proxy's
# -logout-url landing page: it exists precisely for the moment the session cookie has just
# been cleared, so it is unauthenticated by design rather than by oversight.
SKIP_AUTH_PATHS = frozenset({"/healthz", "/readyz", "/metrics", "/signed-out"})

# What the proxy's -pass-access-token flag forwards: the user's own bearer token for the
# hosting cluster. Read by exactly one endpoint (/sign-out) for exactly one purpose
# (revoking that same token), and never logged, stored or echoed — it is a live credential.
ACCESS_TOKEN_HEADER = "X-Forwarded-Access-Token"

# Wall-clock bound on the revocation DELETE. Tight, because it sits inside a user-facing
# navigation: a slow API server may cost the person signing out a few seconds, never a hung
# tab — the redirect that actually ends the session happens whatever this call does.
REVOKE_TIMEOUT_SECONDS = 5.0


# The outcome vocabulary, read OFF THE PARSER rather than restated here. loginlog.py is where an
# outcome is decided, so a new one (a new AD sub-code, say) must not require editing a second list that
# then silently rejects it in a query parameter.
LOGIN_OUTCOMES = tuple(
    v for k, v in vars(loginlog).items() if k.startswith("OUTCOME_") and isinstance(v, str)
)


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


def build_app(settings: Settings, run_poller: bool = True) -> FastAPI:
    # The application asks for "the configured backend" and does not name an engine or its
    # tuning knobs. open_backend() owns that; see gsd/storage.py.
    store: StorageBackend = open_backend(settings)
    elector = LeaderElector(name=settings.leader_lease_name) if settings.leader_election else None
    poller = Poller(store, settings, elector)
    grace = timedelta(seconds=settings.schedule_grace_seconds)

    # Both conditions, not either: the setting is the operator's choice, the proxy flag is
    # whether any identity we see is worth believing. See activity.py.
    activity = ActivityRecorder(
        store,
        enabled=settings.user_activity_enabled and settings.oauth_proxy_enabled,
        flush_interval_seconds=settings.user_activity_flush_seconds,
        retention_days=settings.user_activity_retention_days,
    )
    if settings.user_activity_enabled and not settings.oauth_proxy_enabled:
        log.info(
            "user-activity capture is configured on but the oauth proxy is not enabled; "
            "nothing will be recorded, because without the proxy there is no authentication "
            "and X-Forwarded-User would be caller-supplied"
        )

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

        The unauthenticated paths (/healthz, /readyz, /metrics — oauthProxy.skipAuthRegex)
        need no special case: they carry neither header.
        """
        # Excluded EXPLICITLY, not by assuming they arrive header-less. These three
        # bypass the proxy entirely (oauthProxy.skipAuthRegex), so whether they carry an
        # identity header is decided by the caller — which is exactly the input we must not
        # let decide whether we record.
        if request.url.path not in SKIP_AUTH_PATHS and request.headers.get(INTERACTION_HEADER):
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

    def enrich(cr: dict, now: datetime) -> dict:
        """Attach the computed fields of PLAN §11 — state is derived, never stored."""
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
    def list_clusters() -> list[dict]:
        """Every observed cluster with its poll status and headline counts.

        The overview reads this. An unreachable cluster still appears, carrying its error —
        a cluster this dashboard cannot poll is a thing it exists to report, not a reason to
        omit the row.
        """
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
                    # absent, so the UI can render nothing rather than a healthy-looking 0.
                    "operator_configs": _config_summary(row["id"]),
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
    def list_groupsyncs(cluster_id: str) -> list[dict]:
        """GroupSync CRs on one cluster, with their derived state.

        `state`, `next_expected` and `error_is_current` are computed per request from the
        schedule and the last sync, never stored — a stored state would be wrong the moment
        the clock moved past it.
        """
        require_cluster(cluster_id)
        now = datetime.now(UTC)
        return [enrich(cr, now) for cr in store.groupsyncs(cluster_id)]

    @app.get("/api/clusters/{cluster_id}/groupsyncs/{name}/events")
    def list_events(
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
        cluster_id: str,
        state: str = Query(
            default="all", pattern="^(all|empty|unattributed)$",
            description="`all`; `empty` for groups with zero members, whatever created them; "
                        "`unattributed` for groups no GroupSync CR claims. The two overlap: a "
                        "hand-made group with no members is both."),
    ) -> list[dict]:
        """Synced groups on one cluster, optionally narrowed to a problem state."""
        require_cluster(cluster_id)
        return store.groups(cluster_id, state)

    @app.get("/api/clusters/{cluster_id}/groups/{name}")
    @consistent
    def group_detail(cluster_id: str, name: str) -> dict:
        """One group: its members, the CR that syncs it, and what it grants.

        A group with history but no current state is reported as DELETED rather than 404 —
        it is still named by every membership-change row that mentions it.
        """
        require_cluster(cluster_id)
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
            "owner": owner,
            "members": store.group_members(cluster_id, name),
            "changes": store.membership_events(cluster_id, group_name=name, limit=100),
            # DIRECT bindings only. Role rules are never fetched or expanded, so this is
            # not an effective-permission calculation and must not be presented as one.
            "bindings": store.group_bindings(cluster_id, name),
        }

    @app.get("/api/clusters/{cluster_id}/users")
    def list_users(
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
        """
        require_cluster(cluster_id)
        rows = store.users(cluster_id, limit=limit)
        truncated = len(rows) > limit
        return {
            "cluster": cluster_id,
            "count": min(len(rows), limit),
            "truncated": truncated,
            "limit": limit,
            "users": rows[:limit],
        }

    @app.get("/api/clusters/{cluster_id}/users/{name}")
    @consistent
    def user_detail(cluster_id: str, name: str) -> dict:
        """Reverse lookup: every group this user is in.

        The cluster cannot answer this directly — it means scanning every Group object — yet
        it is the question behind most "why does this person have access?" investigations.
        """
        require_cluster(cluster_id)
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
        cluster_id: str,
        outcome: str | None = Query(
            default=None,
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
        # Which provider NAMES are HTPasswd is deployment configuration — the log carries only the
        # name. Passed to the ungoverned queries so their rows and their count share ONE predicate in
        # the store, and applied per row below for the break_glass label.
        htpasswd = tuple(settings.login_capture_htpasswd_providers)
        status = store.login_capture_status(cluster_id)
        summary = store.login_event_summary(cluster_id, exclude_providers=htpasswd)
        ungoverned = store.ungoverned_login_users(cluster_id, exclude_providers=htpasswd, limit=50)
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
        for row in ungoverned:
            row["has_history"] = bool(row.get("has_history"))

        return {
            "cluster": cluster_id,
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
            "total": summary["total"],
            "limit": limit,
            "truncated": truncated,
            "summary": {
                "distinct_users": summary["distinct_users"],
                "successes": successes,
                "failures": summary["total"] - successes,
                "by_outcome": by_outcome,
                "ungoverned_users": summary["ungoverned_users"],
                "first_at": summary["first_at"],
                "last_at": summary["last_at"],
            },
            # One row per account in no synced group, most recent first. Bounded at 50 and honest
            # about it: summary.ungoverned_users beside it is the whole-set count, from the SAME
            # store predicate, so the two cannot disagree.
            "ungoverned": ungoverned,
            "attempts": attempts,
        }

    @app.get("/api/clusters/{cluster_id}/cluster-access")
    @consistent
    def cluster_access(
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
        access = store.cluster_access_group(cluster_id)
        if not access:
            # NO GATE, which is itself a finding rather than an absence: with no membership clause in
            # any identity provider's filter, every account in the search base can sign in.
            return {
                "cluster": cluster_id,
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
        """
        require_cluster(cluster_id)
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
        total = store.count_direct_user_bindings(
            cluster_id, include_platform=include_platform, namespace=namespace)
        rows = store.direct_user_bindings(
            cluster_id, include_platform=include_platform, namespace=namespace,
            limit=limit, offset=offset)
        return {
            "cluster": cluster_id,
            "note": "direct user grants; migrate these to LDAP-managed groups",
            "by_namespace": store.user_bindings_by_namespace(cluster_id),
            "excluded_platform": store.platform_user_binding_count(cluster_id),
            "namespace": namespace,
            "total": total,
            "limit": limit,
            "offset": offset,
            "truncated": offset + len(rows) < total,
            "bindings": rows,
        }

    @app.get("/api/clusters/{cluster_id}/operator-configs")
    def operator_configs(cluster_id: str) -> dict:
        """Health of the namespace-configuration-operator's CRs on this cluster.

        `present: false` means the CRDs do not exist there — auto-detected, and a
        different truth from "installed with zero CRs". Reconcile conditions only, by
        design: the templates are the operator's business.
        """
        require_cluster(cluster_id)
        return {"cluster": cluster_id, **store.operator_configs(cluster_id)}

    @app.get("/api/clusters/{cluster_id}/membership-changes")
    def membership_changes(
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
        """
        require_cluster(cluster_id)
        # limit + 1, as in list_events — see docs/api-contract.md R3. This log previously
        # cut off at 100 with nothing saying so, which on an audit trail reads as "no
        # further changes" rather than "not shown".
        rows = store.membership_events(cluster_id, limit=limit + 1)
        truncated = len(rows) > limit
        events = rows[:limit]
        return {
            "cluster": cluster_id,
            "count": len(events),
            "limit": limit,
            "truncated": truncated,
            "note": "accumulated from polling; covers only the period since this dashboard started",
            "changes": events,
        }

    @app.get("/api/alerts")
    @consistent
    def list_alerts() -> list[dict]:
        """Everything currently worth a human's attention, across all clusters.

        Ordered by severity. Derived per request from the same stored observations the rest
        of the API serves, so an alert here always has a page behind it.
        """
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
                scope = (
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
                            f"{row['binding_kind']} grants {row['role_name']} {scope} to "
                            f"group {row['group_name']!r}, which the operator used to "
                            f"manage and no longer exists — this binding now grants nobody"
                        ),
                        "severity": "critical",
                    }
                )
        severity_rank = {"critical": 0, "warning": 1}
        alerts.sort(key=lambda a: (severity_rank.get(a["severity"], 9), a["cluster"], a["kind"]))
        return alerts

    metrics_registry = build_registry(store, grace, elector)

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

        TWO logout URLs, because the page has two different exits and only one of them can
        revoke. `logout_url` is the app's own /sign-out, which revokes the OpenShift token
        console-style and then falls through to the proxy's sign_out — the manual link and
        the idle-expiry path both use it, and a link aimed straight at the proxy would
        silently skip the revocation. `proxy_logout_url` is the proxy's bare cookie-clear,
        for the one exit that must NOT route through the app: a session the failover has
        already proven dead cannot reach /sign-out (the proxy would bounce the request into
        a fresh login instead of out of the old one), and it has no live token to revoke.

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
        """
        user = request.headers.get(USER_HEADER)
        authenticated = bool(user) and settings.oauth_proxy_enabled
        return {
            "user": user if settings.oauth_proxy_enabled else None,
            "email": request.headers.get(EMAIL_HEADER) if settings.oauth_proxy_enabled else None,
            "authenticated": authenticated,
            "logout_url": "/sign-out" if authenticated else None,
            # Composed, not hardcoded: tracks a --proxy-prefix override through
            # Settings.oauth_proxy_prefix so the link and the proxy cannot drift apart.
            "proxy_logout_url": (
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

        SELF-ONLY by default. This returns identifiable personnel data — username, email,
        the dates somebody was present and the window they worked in — and it used to hand
        all of it to every authenticated user. The dashboard's usual justification does not
        stretch this far: "you could read the groups with oc anyway" is true of group
        membership and false of who looked at it.

        `userActivity.visibility: all` restores the old behaviour for a deployment that
        genuinely wants it, as a deliberate, documented choice rather than a default.

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

        everyone = settings.user_activity_visibility == "all"
        scope_to = None if everyone else viewer
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
            "scope": "all" if everyone else "self",
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

    @app.get("/sign-out")
    def sign_out(request: Request) -> RedirectResponse:
        """End this session the way the console does: revoke the token, then clear the cookie.

        The console's logout DELETEs the OAuthAccessToken object whose name is derived from
        the bearer token, with the USER's own credentials — the permission is granted to
        authenticated users themselves, so the dashboard's ServiceAccount needs (and gets)
        no write grant. The token arrives on X-Forwarded-Access-Token, which the proxy's
        -pass-access-token flag forwards on every proxied request.

        A GET, deliberately: the control is a plain link and the idle path is a location
        navigation, and both must keep working when the page's scripts are gone. The
        mutation is idempotent and self-scoped — the only token this can revoke is the one
        the request itself presented — so a cross-site drive-by GET costs its victim a
        sign-out and nothing more, the same accepted trade as the proxy's own GET sign_out.

        ORDER IS THE DESIGN. Revoke FIRST, redirect into <prefix>/sign_out SECOND: once the
        proxy clears its cookie the token can never be seen again, so the reverse order
        strands the token alive for its full server-side lifetime (365 days measured on the
        reference cluster). And with -cookie-refresh unset the proxy never revalidates
        mid-session, so revoking under a still-live cookie cannot race the redirect.

        A failed revocation NEVER blocks the exit — a logout that cannot revoke must still
        end the session — so every failure is logged (status only, the token appears in no
        log line) and the redirect happens regardless. /signed-out's wording is written to
        be true in both worlds.
        """
        if not settings.oauth_proxy_enabled:
            # Same refusal, same reasoning as /api/dashboard/activity: without the proxy
            # the token header is whatever the caller typed, and acting on it would let an
            # unauthenticated caller aim a credentialed DELETE at the API server.
            raise HTTPException(
                status_code=403,
                detail="sign-out requires the OAuth proxy; without it there is no session "
                       "to end and a forwarded token would be caller-supplied",
            )
        token = request.headers.get(ACCESS_TOKEN_HEADER)
        if token:
            with kube.self_cluster_client(token, timeout=REVOKE_TIMEOUT_SECONDS) as client:
                revoked, why = kube.revoke_oauth_access_token(client, token)
            if revoked:
                log.info("sign-out: access token %s", why)
            else:
                log.warning(
                    "sign-out: could not revoke the access token — %s. The session still "
                    "ends now; the unrevoked token expires on the cluster's own schedule.",
                    why,
                )
        else:
            log.warning(
                "sign-out request carried no %s header — is the proxy running without "
                "-pass-access-token? The session still ends; the token outlives it.",
                ACCESS_TOKEN_HEADER,
            )
        # 303 rather than the RedirectResponse default 307: the target must be fetched with
        # GET whatever this request was, and 303 is never cached — a cached redirect would
        # skip this handler, and the revocation with it, on the next sign-out. no-store
        # states the same intent explicitly.
        return RedirectResponse(
            url=f"{settings.oauth_proxy_prefix}/sign_out",
            status_code=303,
            headers={"Cache-Control": "no-store"},
        )

    if os.path.isdir(STATIC_DIR):
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    app.state.store = store
    app.state.settings = settings
    return app


def create_app() -> FastAPI:
    """Entrypoint for `uvicorn gsd.api:create_app --factory`."""
    # The offset (%z) is not decoration. TZ is settable on the container, so a log line
    # reading "21:17:59" is UTC on one deployment and local on another, and nothing in the
    # line says which — the same ambiguity the dashboard header had between its own clock
    # and the UTC timestamps beneath it. Correlating a log against a stored timestamp (all
    # of which end in Z) needs the offset present, not inferred from a deployment's values.
    logging.basicConfig(
        level=os.environ.get("GSD_LOG_LEVEL", "INFO"),
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
    return build_app(load_settings(os.environ.get("GSD_CONFIG", "clusters.yaml")))
