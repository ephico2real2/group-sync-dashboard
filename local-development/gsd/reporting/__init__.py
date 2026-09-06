"""The report service — a separate pod that renders evidence documents from a read-only copy
of the dashboard's database, stores them, and is polled by the dashboard for its usage.

docs/specs/SPEC_C3_reporting_microservice.md is the design. The seams, in one place:

* DATA: never the live gsd.db. `snapshot.py` opens the newest `VACUUM INTO` copy the dashboard's
  leader writes under GSD_REPORT_SNAPSHOT_DIR, with `immutable=1&mode=ro` (§4).
* AUTHZ: never decided here. The dashboard mints an HMAC ticket after its own wide-tier check;
  `ticket.py` verifies it and binds it to the proxy's identity header (§5.2). The service token
  (`Authorization: Bearer`) is the dashboard's poller and the schedule Jobs.
* OUTPUT: one data model (`model.py`) rendered twice — `render_html.py`, `render_pdf.py` — so
  the sha256 printed on both is the sha256 of the same canonical JSON.

Importing this package pulls in no PDF library: `render_pdf` imports fpdf2 lazily, so the
dashboard image (which ships the package but not the `report` extra) imports `gsd.reporting.ticket`
without it.
"""

from __future__ import annotations

#: Every route the service serves lives under this prefix, because the oauth-proxy routes the
#: browser's requests to this pod by path (§5.1): `-upstream=https://<svc>:8443/report/`. The
#: prefix is part of the request path the proxy passes through unchanged, so the service must
#: answer on it — and answering on it and nothing else is what makes a stray upstream mapping
#: fail loudly rather than serve.
REPORT_PREFIX = "/report"

#: The header the browser carries the dashboard-minted ticket in. A custom header, so a POST to
#: the service is never a "simple" cross-site request — that is the CSRF defence, stated once.
TICKET_HEADER = "x-gsd-report-ticket"
