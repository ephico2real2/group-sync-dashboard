# The Reporting status page on CRC — the walk behind #149 R5's Definition of Done

Deployed head `cb74ce1` (the stacked branch `feat/149-status-page` on `feat/149-schedules-formats`,
through the Argo Application; `running : cb74ce1795 — verified in-pod`), walked with
`reporting_walk.py` through the OAuth proxy as kubeadmin, Chromium 1280×900 then 375×740, against the
three schedule shapes `environments/crc.yaml` declares. Every line below is the script's own output.

| DoD item | measured |
|---|---|
| the three cards render from live data | `tile : SERVICE · On · PDF pdf/a-2b + HTML · 11 reports enabled · scheduled runs store html+json`; `RUN WINDOW · Open now · 22:00–06:00 America/New_York · Mon–Sun · closes in 3h 42m`; `RETENTION · 2-tier …`; `IN FLIGHT · idle · 0 queued · 0 refused by the window since the service started` |
| the schedule tiles: cadence, retention, enabled, last success, next, status | `nightly-namespace-access … Daily 22:00 … 2 newest · 90 d · On · 2026-09-20 06:16 (3m ago) · 2026-09-21 02:00 (in 19h 40m) · ok`; `quarterly-compliance … Quarterly 06:00 … 12 newest · 2555 d · On · never · 2026-10-01 10:00 (in 11d) · never`; `biweekly-groups … 1st & 16th 06:00 … Paused · never · — · disabled` |
| a paused schedule shows Paused (Next —) | the third row above |
| history paginates server-side; the filters run on the service | `history: all 6 runs | scheduled 4 runs | failed 2 runs | range 1–2 of 2` |
| the link from the Reports page; Back rises to Reports | `link : 6 runs so far. Reporting status, schedules and history →`; `back : ← reports`; `back : to reports` |
| 375 px | `no-x-overflow True | strip columns 2` |
| no uncaught error | `errors : []` |

Captures: `01-status-strip.png`, `02-schedules.png`, `03-history.png`, `04-375.png`. The live check of
R1/R3/R4 that ran on the same deploy is in `docs/REVIEW_schedules_and_formats.md`.
