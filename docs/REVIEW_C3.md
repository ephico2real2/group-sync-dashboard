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

Codex (gpt-5.6-sol, xhigh) reviewed head 7f4825e with a read-only sandbox that could run `helm template`
(defaults, strict duplicate-key parsing, all ten guard probes) and the temp-directory-free tests, but not
the file-backed suites. Two of its refutations (C4, C8) are Cursor's, already applied; the rest:

| Claim | Codex | Decision |
|---|---|---|
| C1 never the live DB | REFUTED — a symlink named like a copy under `/data/report` would be accepted by name and followed into `/data/gsd.db` (the report pod mounts the whole claim), and `immutable=1` on a changing file returns wrong results | **Accepted** — regular files only, judged with `lstat` at listing AND at open; a link or a directory under a copy's name is refused by name. Whoever could plant such a link already writes the volume, so this is defence in depth, and cheap |
| C2 classification | CONFIRMED | — |
| C3 the ticket | REFUTED — `urlsafe_b64decode` discards characters it does not know, so `!!!!` spliced into a ticket still yielded the signed bytes: one credential, many spellings | **Accepted** — strict alphabet, a producible length, and a canonical re-encoding; not an escalation (the signed bytes were unchanged), but a malformed token is refused as the contract says |
| C4 run lifecycle | REFUTED (as Cursor) | applied under Cursor's pass |
| C5 nothing secret or personal | REFUTED — `full_name` is selected and printed in the users report and the rosters | **Rejected** — the brief's "beyond the username" was its own imprecision: a display name is what an access-review document carries (§7.3's rosters name "member, name"), §7.5's list of what never enters a report does not include it, and Cursor read the same code the same way. The brief, not the code, is corrected |
| C6 parameters and the PDF | REFUTED — an integer where a list of names was expected raised `TypeError` (a 500, not a 422); `2026-99-99` passed the date regex; a 10,000-character cell raised fpdf2's "cannot fit on a page" and failed the run; a glyph DejaVu lacks is drawn as the missing-glyph box | **Accepted in part** — `_string_items` makes every wrong shape a `ValidationError`, `date.fromisoformat` makes a date real, integers refuse booleans and floats, strings must be strings; the PDF bounds a cell at `CELL_MAX_CHARS` and marks the cut while the HTML and JSON carry the whole value. **Rejected**: failing a run over one uncovered glyph — measured, fpdf2 substitutes and logs; a document with one boxed emoji is evidence, a failed run is not |
| C7 the chart | CONFIRMED (helm renders and every guard probe executed) | — |
| C8 the dashboard side | REFUTED (the watermark, as Cursor) and: every pull exception was `unreachable`, including a 200 with a body that is not JSON | **Accepted** — `httpx.TransportError` is `unreachable`; anything else on a reachable service is `error`, as the alert's description promises |
| C9 the UI | CONFIRMED | — |
| C10 images and workflows | REFUTED — **the report-image publish step had landed under the `sbom` job** while reading `steps.creds` and `steps.release`, which exist only in `publish`: step outputs are job-local, so its condition could never hold and the report image would never have been pushed by CI; the image proofs lacked `jinja2`/`markupsafe` | **Accepted** — the step is in `publish`, after the dashboard's build, with its own `DIGEST_FILE` and a second pair of job outputs; and, beyond the brief's claim, the report image now gets the same SBOM and keyless attestation as the dashboard's (Codex's additional finding: it had "no equivalent digest/SBOM/attestation path") — `sbom` and `attest` are a two-leg matrix over the two `<image, digest>` pairs, one definition for both (`DESIGN_supply_chain.md` D10; the report SBOM is `sbom-report-<sha>`). A workflow-semantics test holds every `steps.<id>.`, `needs.<job>.outputs.<name>` and `matrix.<key>` reference in the three workflows to a definition — GitHub resolves an unknown one to an empty string, not an error. actionlint 1.7.12 with shellcheck passes the file. The proofs import `jinja2` and `markupsafe` |

Codex's other additional findings were Cursor's (the cluster id in `Content-Disposition`, the probes'
unclosed `Snapshot`), applied there; its reading of `test_containerfile_report.py`'s wrong marker was
right and is fixed.

## The orchestrator's verification of the publish-job fix, 2026-09-11

The C10 fix (the two-image `publish.yml`) was verified before commit by three independent passes over
the working tree — GitHub Actions semantics against the official contexts, syntax and expressions
references and the pinned actions' sources; behaviour preservation through ten failure scenarios traced
in the YAML; and a mutation harness running the new tests against eleven reintroduced defects on an
isolated copy — each finding then judged by two further skeptics. Measured: all eleven mutations were
killed by the test whose message names the defect, actionlint 1.7.12 with shellcheck passes the file, and
the contexts table settles that `matrix` is not readable by a job-level `if`. Accepted from that pass:
the manual release route (the release decision's warning, `helm.yaml`'s label error, the script header,
`RELEASING.md`) named one script where a release is now two images; on a release push the dashboard's
aliases move before the report build, so a failed report build leaves them on a digest the run never
signs and a dispatch cannot move them — D10 now states the case and the recovery; the reference test's
docstring claimed YAML comments were searched (they are dropped by the loader; shell comments inside
`run:` are held — measured); `strategy.get("fail-fast")` so an absent key, GitHub's default, is the same
defect as `true`. Recorded, not changed: `needs.sbom.result` for a matrix job is one result per job by
the documented model, confirmed only by GitHub's community answer — to be confirmed on the first run
with a red leg; the two job display names changed with the matrix; nothing labels the report image by
chart version. Found beside it, by the full suite: three report-server tests built their app on the real
clock while the module mints tickets at import time, so a suite that reaches the module after the 300 s
TTL answered 401 — reproduced by shifting the mint time, fixed by giving every app the fixture's frozen
clock.

## Second pass — head 18438c5, 2026-09-11

A twelve-claim brief on the fixed head: each accepted first-pass fix, then what the first pass never
named — the merge as a release push, two invocations in a row, the registry side. Cursor (ask mode, no
shell: it read the head and the installed packages and marked what it could not run) and Codex
(gpt-5.6-sol, xhigh, a shell). Every verdict re-checked here before a decision; every accepted finding
measured first.

| Claim | Cursor | Codex | Decision |
|---|---|---|---|
| C1 the ticket's one spelling | CONFIRMED — and a refused ticket is a **403** (`principal` maps every `TicketError` but expiry to 403; only "ticket has expired" is the 401) | _(pending)_ | — ; the brief's "401" was the brief's error, corrected here |
| C2 regular-file snapshots | CONFIRMED; a hard link IS a regular file and would pass — defence in depth only, since planting one needs write on the volume the report mount does not have | _(pending)_ | recorded, no change |
| C3 every wrong shape is a 422 | REFUTED — `int()` accepts `" 1"`, `"1_000"`, `"\t1\n"`; a `str` parameter stringified a number | _(pending)_ | **Accepted** — an integer string must spell `-?[0-9]+`; a string is a string. Cursor's snippet taken in substance; the test extends the first pass's, with `""` asserted as the default it deliberately is |
| C4 no cell fails a run | REFUTED — 600 newlines is a 600-line row, "cannot be rendered on a single page" | _(pending)_ | **Accepted on the fact, snippet in part** — measured on the first-pass head: 600 and 700 newlines fail; `W`×600, full-width `Ｗ`×600, `@`×600 and CJK×600 render. Whitespace is collapsed before the cap; the cap stays at 600 (Cursor's 240 was reasoned from column width, not measured, and every wide-glyph case measured at 600 renders). The HTML and JSON keep the raw value |
| C5 pull outcomes | REFUTED — a 200 carrying JSON without `runs` recorded nothing and counted `ok` | _(pending)_ | **Accepted** — the body must be a dict whose `runs` is a list, else `error`; five wrong shapes tested |
| C6 prune / since / write | CONFIRMED; a run that stays `running` delays later runs (the watermark holds below it), never skips them; a restart marks it failed and the feed resumes | _(pending)_ | recorded |
| C7 the release push | PLAUSIBLE — and volunteered: `sbom`'s `if` names no `success()`, so a red publish "still runs" the catalogue | _(pending)_ | **Rejected** — GitHub's expressions reference: "A default status check of `success()` is applied unless you include one of these functions"; the `sbom` condition has none, so a red publish skips it (the first pass quoted the same line; actionlint models it). A comment on the condition now says so, and the test that pins the line is the guard. The registry finding (a new repository is created private) was already on the head in `RELEASING.md` — Cursor's quotation of that row inverted "private" to "public"; the file says private |
| C8 the wrapper's `--release-tags` | CONFIRMED (traced, not run) | _(pending)_ | — |
| C9 the frozen clock | CONFIRMED (every `build_report_app(` passes `clock=`) | _(pending)_ | — |
| C10 the references test | CONFIRMED; exclude-only keys are not definitions | _(pending)_ | — |
| C11 the docs | REFUTED on one D10 sentence ("withholds both images' catalogue") | _(pending)_ | **Rejected** with C7: the sentence is true of the YAML under the implied `success()` |
| C12 the next real use | PLAUSIBLE (not run) | _(pending)_ | the suite and the chart's switch states ran here (below) |

**Found by CI on this head, not by a reviewer.** The `image` job went red at the dashboard image's
build-time proof: the RPM database directory held `['.keyring.lock', '.rpm.lock', 'rpmdb.sqlite']`,
"not the base's two files". Nothing in the PR touches the recipe; both `hi/python:3.14` tags were
rebuilt on 2026-09-09 (3.14.7, measured with `skopeo inspect`), after the last green run on 2026-09-06,
and the builder's rpm now leaves `.keyring.lock` after the pack stage's erase. Both proofs now hold the
rule — `rpmdb.sqlite` plus rpm's dot-lock files and nothing else — instead of a list of two names;
the pinning test, the recipe's comment and `DESIGN_hardened_image.md` say so. The rule was exercised
against six listings (the old pair, the new triple, a WAL side file, a leftover `Packages`, a missing
database, a stray dotfile): the first two pass, the rest are refused.
