"""Read-only HTTP API (PLAN §11).

No endpoint returns a token or accepts one from the browser. The frontend talks only to this
service and never holds a cluster credential (PLAN §9).
"""

from __future__ import annotations

import functools
import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from . import __version__
from . import state as st
from .activity import EMAIL_HEADER, INTERACTION_HEADER, USER_HEADER, ActivityRecorder
from .config import Settings, load_settings
from .leader import LeaderElector
from .metrics import build_registry
from .poller import Poller
from .storage import StorageBackend, open_backend

log = logging.getLogger(__name__)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

# Mirrors oauthProxy.skipAuthRegex. Requests here reach the app WITHOUT authentication, so
# nothing they claim about identity can be believed or recorded.
SKIP_AUTH_PATHS = frozenset({"/healthz", "/readyz", "/metrics"})


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

    app = FastAPI(title="GroupSync dashboard", version="0.1.0", lifespan=lifespan)

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
                    "group_count": counts["total"],
                    "empty_groups": counts["empty"],
                    "unattributed_groups": counts["unattributed"],
                    "oldest_last_sync": store.oldest_last_sync(row["id"]),
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
        require_cluster(cluster_id)
        now = datetime.now(UTC)
        return [enrich(cr, now) for cr in store.groupsyncs(cluster_id)]

    @app.get("/api/clusters/{cluster_id}/groupsyncs/{name}/events")
    def list_events(
        cluster_id: str,
        name: str,
        since: str | None = None,
        limit: int = Query(default=200, ge=1, le=2000),
    ) -> dict:
        require_cluster(cluster_id)
        events = store.sync_events(cluster_id, name, since, limit)
        return {
            "cluster": cluster_id,
            "groupsync": name,
            "count": len(events),
            # The timeline is accumulated, not fetched — it only covers the period this
            # dashboard has been running (PLAN §2). Saying so stops an empty list being
            # read as "the operator never synced".
            "note": "accumulated from polling; covers only the period since this dashboard started",
            "events": events,
        }

    @app.get("/api/clusters/{cluster_id}/groups")
    def list_groups(
        cluster_id: str,
        state: str = Query(default="all", pattern="^(all|empty|unattributed)$"),
    ) -> list[dict]:
        require_cluster(cluster_id)
        return store.groups(cluster_id, state)

    @app.get("/api/clusters/{cluster_id}/groups/{name}")
    @consistent
    def group_detail(cluster_id: str, name: str) -> dict:
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
        cluster_id: str, limit: int = Query(default=1000, ge=1, le=10000)
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
            "groups": groups,
            "changes": changes,
            # Reachable through their group memberships. Each row carries via_group, so
            # "why do they have this?" is answerable without a second lookup.
            "bindings": store.user_bindings(cluster_id, name),
        }

    @app.get("/api/clusters/{cluster_id}/bindings/findings")
    def binding_findings(cluster_id: str) -> dict:
        """Bindings whose Group subject resolves to no Group object, classified.

        Three tiers rather than two: on a real cluster the large majority of unresolvable
        Group subjects are built-in virtual groups (`system:serviceaccounts:*`,
        `system:authenticated`), which authorise real access and have no object by design.
        Reporting those as broken buries the few that are.
        """
        require_cluster(cluster_id)
        # Every binding, including the ones that resolve normally. A view labelled
        # "bindings" that omitted the healthy majority (74 of 228 here) misrepresented the
        # cluster; the caller filters, rather than the API deciding what is worth seeing.
        rows = store.all_bindings(cluster_id)
        by_tier: dict[str, list[dict]] = {
            "ok": [], "dangling": [], "unresolved": [], "built_in": []
        }
        for row in rows:
            by_tier.setdefault(row["finding"], []).append(row)
        return {
            "cluster": cluster_id,
            "note": "direct bindings only; role rules are not evaluated",
            "total": len(rows),
            "counts": {tier: len(v) for tier, v in by_tier.items()},
            **by_tier,
        }

    @app.get("/api/clusters/{cluster_id}/membership-changes")
    def membership_changes(
        cluster_id: str, limit: int = Query(default=100, ge=1, le=1000)
    ) -> dict:
        require_cluster(cluster_id)
        events = store.membership_events(cluster_id, limit=limit)
        return {
            "cluster": cluster_id,
            "count": len(events),
            "note": "accumulated from polling; covers only the period since this dashboard started",
            "changes": events,
        }

    @app.get("/api/alerts")
    @consistent
    def list_alerts() -> list[dict]:
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
                groups=store.groups(cluster_id, "all"),
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
        because in that mode the caller supplied it themselves.
        """
        user = request.headers.get(USER_HEADER)
        return {
            "user": user if settings.oauth_proxy_enabled else None,
            "email": request.headers.get(EMAIL_HEADER) if settings.oauth_proxy_enabled else None,
            "authenticated": bool(user) and settings.oauth_proxy_enabled,
        }

    @app.get("/api/dashboard/activity")
    def dashboard_activity(
        request: Request,
        since: str | None = Query(None, description="UTC date, YYYY-MM-DD"),
        limit: int = Query(500, ge=1, le=5000),
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
        return {
            "enabled": activity.enabled,
            "retention_days": settings.user_activity_retention_days,
            "scope": "all" if everyone else "self",
            "viewer": viewer,
            "activity": store.user_activity(
                since_day=since, limit=limit, user_name=None if everyone else viewer
            ),
        }

    @app.get("/api/version")
    def version() -> dict:
        """What is actually running, provable back to a commit.

        Stamped into the image at build time. `dirty: true` means the build included
        uncommitted changes, so no commit reproduces it — which is the honest answer when
        someone asks "is my fix in there?".
        """
        commit = os.environ.get("GSD_GIT_COMMIT", "unknown")
        return {
            "leader": elector.is_leader if elector is not None else None,
            "version": os.environ.get("GSD_VERSION", __version__),
            "commit": commit,
            "branch": os.environ.get("GSD_GIT_BRANCH", "unknown"),
            "dirty": commit.endswith("-dirty"),
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

    if os.path.isdir(STATIC_DIR):
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    app.state.store = store
    app.state.settings = settings
    return app


def create_app() -> FastAPI:
    """Entrypoint for `uvicorn gsd.api:create_app --factory`."""
    logging.basicConfig(
        level=os.environ.get("GSD_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
    )
    return build_app(load_settings(os.environ.get("GSD_CONFIG", "clusters.yaml")))
