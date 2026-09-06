# Review — PR #91, C3: reporting as a microservice

Adversarial second-opinion pass, 2026-09-06, on the ten-claim brief for #91
(`docs/specs/SPEC_C3_reporting_microservice.md` applied as amended by its orchestrator's notes; application
0.18.0, chart 0.20.0, the report image at the same appVersion). Cursor (Grok 4.6 high fast, ask mode) and
Codex (gpt-5.6-sol, xhigh) reviewed the head after the first CRC deploy; every verdict was re-checked here
before a decision, and every accepted finding came with a test that failed before its change.

## Live run on the reference cluster

Head e194d49 (the spec applied, the release bump, the lab release script shipping both images), deployed
with `environments/crc.yaml` unchanged — reporting is on by default:

| Measured | Value |
|---|---|
| report pod | `1/1 Running`, restarts 0; readiness `/report/readyz` answers in 15–26 ms over TLS |
| first snapshot | written by the leader 32 s after the dashboard came up, 1,458,176 bytes, schema 11; `/report/api/snapshot` (service token, service-ca CA) answers `available: true, age_seconds: 226` |
| proxy | `-upstream=https://group-sync-dashboard-report.group-sync-dashboard.svc:8443/report/` and `-upstream-ca=/etc/gsd/service-ca/service-ca.crt` beside the loopback upstream — the shipped v4.15 proxy has the flag (pre-flight measured) |
| usage pull | `GET /report/api/usage?limit=500` answers 200 over TLS every cycle the report pod is Ready |
| the one gap | two `ConnectError: Connection refused` pulls: the first before the report pod was Ready, the second while its pod was being replaced — `FailedScheduling: 0/1 nodes are available: 1 Insufficient cpu` for 12 s on a node at **99 % CPU requests**. A lab-capacity fact, not a code path; the pull counts it as `unreachable` and the next cycle recovers |
| node | `cpu 4792m (99 %) requests` — the reference cluster is at its scheduling limit with reporting on |
| a real login | `kubeadmin` through OpenShift's login page (the `developer` htpasswd provider, as D1 measured); `/api/version` `features.reporting: true`; the Reports tab lists eleven entries, none disabled (login capture is on in the lab) |
| a real run | `namespace-access` for `group-sync-dashboard,openshift-authentication`: `done` in 1.8 s, sha256 `6a3ee636…`, data as of the snapshot taken 4.6 min earlier; `generated_by: kubeadmin (proxy-verified, ticket from the dashboard)` |
| the PDF | `gsd_crc-local_namespace-access_20260906T035313Z.pdf`, 32,692 bytes: `%PDF`, `<pdfaid:part>2</pdfaid:part>`, `/OutputIntent`, `/FontFile2` — the PDF/A-2b markers §6.2 measured |
| the JSON | same sha256 as the run; sections `Provenance and coverage`, one per namespace; `coverage.attests_absence: false` (rbac.namespaces is off in the lab, and the report says so) |
| the dashboard's record | `/api/dashboard/reports` at the usage tier: `scope: all, total: 3` from the poller's pull — the report service's runs recorded without a write on the dashboard's API |

## Verdicts — Cursor

Read-only (ask mode blocked the shell; every proposed test was run here before a decision). Head 7f4825e.

| Claim | Cursor | Decision |
|---|---|---|
| C1 never the live DB, cannot write | CONFIRMED | — |
| C2 classification is the Store's | CONFIRMED | — |
| C3 the ticket | CONFIRMED | — |
| C4 run lifecycle | REFUTED — `prune` bounded EVERY status by `maxRuns`, so a 202'd run still queued could lose its directory: GET 404 after a 202, the worker's `get` None and a silent skip | **Accepted** — `prune` considers finished runs only; `write` recreates the run directory; Cursor's test taken |
| C5 nothing secret or personal | CONFIRMED | — |
| C6 parameters and the PDF | CONFIRMED | — |
| C7 the chart | CONFIRMED | — |
| C8 the dashboard side | REFUTED — `since` published any finished run with `id > since_id`, and a QueueFull failure is finished at once with the newest id, so the dashboard's `MAX(id)` watermark moved past eight older runs still in flight and hid them from every later pull | **Accepted** — `since` never returns a finished run whose id is above the oldest queued or running id; the page resumes when that run settles. Cursor's test taken (the watermark stays put, then advances past both) |
| C9 the UI | CONFIRMED | — |
| C10 images and workflows | CONFIRMED | — |

Both refutations are one assumption — id order taken for finish order — applied twice; Cursor said so.

Beyond the brief: (1) the probes constructed `Snapshot(...)` without closing it, pinning a copy the writer
wants to prune until garbage collection — **accepted**, every probe opens and closes within the request, with
a test that every opened connection is closed; (2) `Content-Disposition` interpolated the caller-supplied
cluster id — **accepted**, `RunRequest.cluster` is constrained to `^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$` and a
quote, a CRLF, an empty or an over-long id is 422; (3) `Run.public()` carries `error`, which for a
`SnapshotError` names the snapshot directory — **rejected**: the reader is the wide tier (the administrator
who operates the volume), the message IS the remedy, and the dashboard's own table deliberately stores no
error text; (4) a non-BMP or CJK glyph absent from DejaVu Sans would fail the run — **rejected on
measurement**: fpdf2 2.8.8 renders such a cell with its missing-glyph box and a log line naming the code
points (`Font MPDFAA+DejaVuSansBook is missing the following glyphs: …`), the run completes (21,382 bytes
for a cell mixing Fraktur, an emoji and CJK); the limitation is recorded in the design record; (5)
`poll_outcome.message` printed on page one when the last poll was not `ok` — **rejected**: it is the
dashboard's own poll status text, already shown to the wide tier on the Overview, and the spec's provenance
block asks for it by name.

## Verdicts — Codex

_(pending)_
