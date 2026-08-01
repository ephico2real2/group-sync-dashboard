"""Read-only HTTP API (PLAN §11).

No endpoint returns a token or accepts one from the browser. The frontend talks only to this
service and never holds a cluster credential (PLAN §9).
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import state as st
from .config import Settings, load_settings
from .poller import Poller
from .store import Store

log = logging.getLogger(__name__)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def build_app(settings: Settings, run_poller: bool = True) -> FastAPI:
    store = Store(settings.db_path)
    poller = Poller(store, settings)
    grace = timedelta(seconds=settings.schedule_grace_seconds)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if run_poller:
            poller.start()
        else:
            # Still register configured clusters so the overview lists them as
            # never-polled rather than omitting them entirely.
            for cluster in settings.clusters:
                store.upsert_cluster(cluster.name, cluster.api_url, cluster.enabled)
        yield
        poller.stop()
        store.close()

    app = FastAPI(title="GroupSync dashboard", version="0.1.0", lifespan=lifespan)

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

    @app.get("/api/clusters")
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
    def group_detail(cluster_id: str, name: str) -> dict:
        require_cluster(cluster_id)
        detail = store.group_detail(cluster_id, name)
        if detail is None:
            raise HTTPException(status_code=404, detail=f"unknown group {name!r}")
        owner = None
        if detail.get("sync_provider"):
            for cr in store.groupsyncs(cluster_id):
                if cr.get("provider_key") == detail["sync_provider"]:
                    owner = {"name": cr["name"], "namespace": cr["namespace"],
                             "schedule": cr["schedule"]}
                    break
        return {
            **detail,
            "owner": owner,
            "members": store.group_members(cluster_id, name),
            "changes": store.membership_events(cluster_id, group_name=name, limit=100),
        }

    @app.get("/api/clusters/{cluster_id}/users")
    def list_users(cluster_id: str) -> list[dict]:
        require_cluster(cluster_id)
        return store.users(cluster_id)

    @app.get("/api/clusters/{cluster_id}/users/{name}")
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
        severity_rank = {"critical": 0, "warning": 1}
        alerts.sort(key=lambda a: (severity_rank.get(a["severity"], 9), a["cluster"], a["kind"]))
        return alerts

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

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
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))

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
