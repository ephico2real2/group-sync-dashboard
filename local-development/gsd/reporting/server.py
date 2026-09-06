"""The report service's HTTP API — everything under /report (REPORT_PREFIX).

Its own contract, held by tests/test_reporting_server.py the way tests/test_api_contract.py holds
the dashboard's: every route documented with a first-line sentence, every Query described, one and
only one non-GET (POST /report/api/runs — the trigger that must not live on the dashboard), and
the three unauthenticated paths listed by name. Auth is a dependency (`principal`), so a route
cannot be added without saying who may call it.
"""

from __future__ import annotations

import hmac
import logging
import os
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from .. import TITLE, __version__
from ..activity import USER_HEADER
from . import REPORT_PREFIX, TICKET_HEADER
from .artifacts import FORMATS, ArtifactStore, Run, new_run_id
from .catalogue import REGISTRY, ValidationError, validate_params
from .config import ReportSettings, load_report_settings
from .metrics import ReportSignals, build_report_registry
from .runs import QueueFull, RunManager
from .snapshot import Snapshot, SnapshotError, newest_snapshot
from .ticket import TicketError, load_secret, verify

log = logging.getLogger(__name__)

#: The same sentence the dashboard's gate uses (gsd/api.py#require_admin_tier). Two doors, one
#: wording, so a caller comparing them can tell they are the same control.
REFUSAL = ("For administrators only. This view reports the cluster's own RBAC binding surface and "
           "operator configuration rather than anything belonging to the reader.")
UNAUTHENTICATED = frozenset({f"{REPORT_PREFIX}/healthz", f"{REPORT_PREFIX}/readyz", f"{REPORT_PREFIX}/metrics"})


class Principal(BaseModel):
    kind: str            # "viewer" | "service"
    name: str
    note: str


class RunRequest(BaseModel):
    report: str = Field(description="A catalogue name, e.g. namespace-access.")
    cluster: str = Field(description="The cluster id as the dashboard names it.")
    params: dict = Field(default_factory=dict, description="Parameters per the report's spec; unknown keys are refused.")
    formats: list[str] = Field(default_factory=lambda: ["html", "pdf"], description="Subset of html, pdf; json is always written.")
    schedule: str | None = Field(default=None, description="Service callers only: the schedule name this run is for.")


def build_report_app(settings: ReportSettings, *, secret: bytes | None = None, clock=None) -> FastAPI:
    secret = secret if secret is not None else load_secret(settings.token_file)
    now = clock or (lambda: datetime.now(UTC))
    store = ArtifactStore(settings.artifact_dir)
    signals = ReportSignals()
    runs = RunManager(settings, store, signals, clock=now)

    def snapshot_age() -> float | None:
        try:
            return Snapshot(newest_snapshot(settings.snapshot_dir)).info().age_seconds(now())
        except (SnapshotError, OSError):
            return None

    registry = build_report_registry(signals, store, runs, settings.snapshot_dir, snapshot_age)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        runs.start()
        yield
        runs.stop()

    app = FastAPI(title=f"{TITLE} — report service", version=__version__, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=f"{REPORT_PREFIX}/api/openapi.json",
                  description="Renders evidence reports from a read-only snapshot of the dashboard's database. "
                              "Every request but the three probe paths needs a dashboard-minted ticket or the service token.")

    # -- who is calling -----------------------------------------------------------------------

    def principal(request: Request) -> Principal:
        """Ticket or service token; nothing else. Order matters: a bearer token is the poller or a
        Job and never carries a ticket, so it is checked first and a stray ticket beside it is
        ignored rather than argued with."""
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            if hmac.compare_digest(auth[7:].strip().encode("utf-8"), secret):
                return Principal(kind="service", name="service", note="service token")
            raise HTTPException(status_code=401, detail="service token does not match")
        ticket = request.headers.get(TICKET_HEADER)
        if not ticket:
            raise HTTPException(status_code=401, detail="a report ticket is required (X-GSD-Report-Ticket)")
        try:
            claims = verify(secret, ticket, request.headers.get(USER_HEADER), now().timestamp())
        except TicketError as exc:
            # A refused ticket is a 403 with the gate's own sentence: the browser shows the reader
            # the same refusal the dashboard would, and the reason goes to the log, not the wire.
            # The one exception is expiry: a 401, which reportFetch answers by minting a fresh
            # ticket exactly once (§9.11), so a page left open past the TTL keeps working.
            log.info("ticket refused: %s", exc)
            if str(exc) == "ticket has expired":
                raise HTTPException(status_code=401, detail="the report ticket expired; mint a new ticket") from exc
            raise HTTPException(status_code=403, detail=REFUSAL) from exc
        return Principal(kind="viewer", name=claims["viewer"], note="proxy-verified, ticket from the dashboard")

    def service_only(p: Principal = Depends(principal)) -> Principal:
        if p.kind != "service":
            raise HTTPException(status_code=403, detail="the usage feed is read by the dashboard, not by viewers")
        return p

    # -- probes and metrics (unauthenticated; reachable only on the report Service) -------------

    @app.get(f"{REPORT_PREFIX}/healthz")
    def healthz() -> dict:
        """Liveness: the process answers."""
        return {"status": "ok"}

    @app.get(f"{REPORT_PREFIX}/readyz")
    def readyz() -> dict:
        """Readiness: the artefact volume is writable and a snapshot exists to render from.

        A missing snapshot is 503 with the reason: the dashboard's leader has not written one yet,
        or the data volume is not mounted — either way a run would fail, so the pod says not ready.
        """
        try:
            probe = os.path.join(settings.artifact_dir, ".readyz")
            with open(probe, "w", encoding="utf-8") as fh:
                fh.write("ok")
            os.remove(probe)
        except OSError as exc:
            raise HTTPException(status_code=503, detail=f"artifact volume not writable: {exc}") from exc
        try:
            info = Snapshot(newest_snapshot(settings.snapshot_dir)).info()
        except SnapshotError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {"status": "ready", "snapshot": info.stamp, "schema": info.schema_version}

    @app.get(f"{REPORT_PREFIX}/metrics")
    def metrics() -> Response:
        """Prometheus exposition. Counts and seconds per report name; never a person."""
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    # -- the catalogue --------------------------------------------------------------------------

    @app.get(f"{REPORT_PREFIX}/api/reports")
    def list_reports(p: Principal = Depends(principal)) -> dict:
        """The catalogue: every report, whether this deployment enabled it, and its parameter specs.

        The page renders its forms from `params`; a disabled report is listed with `enabled: false`
        and its values key, so "why is this greyed out" has an answer on the wire.
        """
        return {"reports": [spec.as_json(spec.name in settings.enabled_reports) for spec, _ in REGISTRY.values()],
                "pdf": {"enabled": settings.pdf_enabled, "variant": settings.pdf_variant},
                "viewer": p.name if p.kind == "viewer" else None}

    @app.get(f"{REPORT_PREFIX}/api/snapshot")
    def snapshot_info(p: Principal = Depends(principal)) -> dict:
        """The snapshot a run started now would read: its stamp, age and schema level, or why there is none."""
        try:
            info = Snapshot(newest_snapshot(settings.snapshot_dir)).info()
        except SnapshotError as exc:
            return {"available": False, "reason": str(exc)}
        return {"available": True, "stamp": info.stamp, "age_seconds": round(info.age_seconds(now())),
                "schema_version": info.schema_version, "bytes": info.bytes}

    # -- runs -----------------------------------------------------------------------------------

    @app.post(f"{REPORT_PREFIX}/api/runs", status_code=202)
    def create_run(body: RunRequest, p: Principal = Depends(principal)) -> dict:
        """Queue one report run; 202 with the run id, then poll GET /report/api/runs/{id}.

        THE ONE WRITE IN EITHER SERVICE'S API, and it lives here, not on the dashboard: the
        dashboard's contract is GET-only (tests/test_api_contract.py R6) and a GET must not cause
        work. The caller is a wide-tier viewer (ticket) or the service token (a schedule Job).
        Parameters are validated now so a bad request is a 422 here rather than a failed run later.
        """
        if body.report not in REGISTRY:
            raise HTTPException(status_code=404, detail=f"unknown report {body.report!r}")
        if body.report not in settings.enabled_reports:
            raise HTTPException(status_code=404, detail=f"report {body.report!r} is not enabled on this deployment")
        spec, _ = REGISTRY[body.report]
        try:
            params = validate_params(spec, body.params)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        bad = sorted(set(body.formats) - {"html", "pdf"})
        if bad:
            raise HTTPException(status_code=422, detail=f"unknown format(s) {bad}; json is always written")
        if "pdf" in body.formats and not settings.pdf_enabled:
            raise HTTPException(status_code=422, detail="PDF output is disabled on this deployment (reporting.pdf.enabled)")
        if body.schedule and p.kind != "service":
            raise HTTPException(status_code=422, detail="only the service token may name a schedule")
        by = f"schedule:{body.schedule}" if body.schedule else p.name
        run = Run(id=new_run_id(now()), report=body.report, cluster=body.cluster, params=params,
                  formats=sorted(set(body.formats)), generated_by=by,
                  generated_by_note="unattended (service token)" if p.kind == "service" else p.note,
                  schedule=body.schedule, requested_at=now().strftime("%Y-%m-%dT%H:%M:%SZ"))
        try:
            runs.submit(run)
        except QueueFull as exc:
            raise HTTPException(status_code=429, detail="the render queue is full; try again shortly") from exc
        return run.public()

    @app.get(f"{REPORT_PREFIX}/api/runs")
    def list_runs(p: Principal = Depends(principal),
                  report: str | None = Query(default=None, description="Only runs of this report."),
                  limit: int = Query(default=100, ge=1, le=1000, description="Page size, newest first. `total` and `truncated` describe the whole set."),
                  offset: int = Query(default=0, ge=0, description="Page offset.")) -> dict:
        """Runs, newest first, with status, sizes and the data sha256 — the Reports tab's recent-runs table."""
        rows, total = store.list(report=report, limit=limit, offset=offset)
        return {"runs": [r.public() for r in rows], "total": total, "limit": limit, "offset": offset,
                "truncated": offset + len(rows) < total, "queued": runs.queued()}

    @app.get(f"{REPORT_PREFIX}/api/runs/{{run_id}}")
    def get_run(run_id: str, p: Principal = Depends(principal)) -> dict:
        """One run: status (queued|running|done|failed), timings, sha256, and which artefacts exist."""
        run = store.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="no such run")
        return run.public()

    @app.get(f"{REPORT_PREFIX}/api/runs/{{run_id}}/artifact")
    def get_artifact(run_id: str, p: Principal = Depends(principal),
                     format: str = Query(default="pdf", pattern="^(json|html|pdf)$", description="json, html or pdf."),
                     download: bool = Query(default=True, description="Send as an attachment (default) or inline.")) -> Response:
        """The artefact bytes; 404 until the run is done. Cache-Control: no-store — evidence is fetched, not cached."""
        run = store.get(run_id)
        if run is None or run.status != "done":
            raise HTTPException(status_code=404, detail="no such run, or not finished")
        data = store.read(run_id, format)
        if data is None:
            raise HTTPException(status_code=404, detail=f"this run has no {format} artefact")
        media = {"json": "application/json", "html": "text/html; charset=utf-8", "pdf": "application/pdf"}[format]
        stamp = run.finished_at.replace("-", "").replace(":", "") if run.finished_at else run_id[:15]
        name = f"gsd_{run.cluster}_{run.report}_{stamp}.{format}"
        headers = {"Cache-Control": "no-store", "X-GSD-Report-SHA256": run.sha256 or ""}
        if download:
            headers["Content-Disposition"] = f'attachment; filename="{name}"'
        return Response(data, media_type=media, headers=headers)

    # -- the dashboard's pull -------------------------------------------------------------------

    @app.get(f"{REPORT_PREFIX}/api/usage")
    def usage(p: Principal = Depends(service_only),
              since_id: str | None = Query(default=None, description="Return runs with an id greater than this (ids sort chronologically)."),
              limit: int = Query(default=500, ge=1, le=5000, description="Page size, oldest first; `next_since_id` continues.")) -> dict:
        """Finished runs for the dashboard to record — who generated which report, when, with what outcome.

        SERVICE TOKEN ONLY. The dashboard pulls this on its poll thread and stores it in
        `report_run` (migration 11); it is how "the report service publishes its use to the
        dashboard" without a write on the dashboard's API. Viewers read the result from the
        dashboard at the usage tier, never from here.
        """
        rows = store.since(since_id, limit)
        return {"runs": [r.public() for r in rows], "next_since_id": rows[-1].id if rows else since_id,
                "truncated": len(rows) == limit, "service_version": __version__}

    app.state.store, app.state.runs, app.state.settings = store, runs, settings
    return app


def create_report_app() -> FastAPI:
    """Entrypoint for `uvicorn gsd.reporting.server:create_report_app --factory`."""
    from ..api import _resolve_log_level
    level, complaint = _resolve_log_level(os.environ.get("GSD_LOG_LEVEL"))
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)-7s %(name)s %(message)s")
    if complaint:
        log.warning("%s", complaint)
    return build_report_app(load_report_settings())
