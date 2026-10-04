# SPEC F4 — webhook delivery of scheduled reports: one CloudEvent per finished run, the URL in a mounted Secret and never printed, retried inside the Job's deadline (#109)

| | |
|---|---|
| Programme | Epic F (#386), reports: honest seals, more formats, diffs and delivery. Build step 4 of 6: a scheduled report reaches someone without their opening the dashboard |
| Batch | F — reports |
| Release | — (post-programme; its own PR and its own review) |
| Version on release | app 4.4.0, chart 0.67.0 |
| Version note | Image content (`gsd/reporting/trigger.py` gains delivery), so the next application MINOR, 4.4.0 (`docs/specs/README.md`, the version ladder). The chart takes a MINOR because a value key is added (`reporting.schedules[].deliver`), by its own rule (`charts/group-sync-dashboard/Chart.yaml#MAJOR and MINOR for behaviour`) and its history (0.66.0: "MINOR: `platformUsers` …"; 0.66.5 to 0.66.7 were PATCHes because they added no key). Read on `0a4a366d` (application 4.3.0, chart 0.66.7). W1 was `specified` at chart 0.67.0; by SPEC_E5's rule (a `specified` spec names a chart version above `Chart.yaml` and above every other `specified` claim) this spec takes 0.67.0 as the next to be built and W1 moves to 0.68.0, its index row and its header in this spec's own commit. A release that lands first makes the version blocks fail their check; the implementing pull request corrects them here first |
| Issue | [#109](https://github.com/ephico2real2/group-sync-dashboard/issues/109) |
| Status | merged |
| Source | OB1-lite's research and specification of 2026-10-04, from the issue's refined body (2026-09-26), `docs/DESIGN_reporting_output_and_delivery.md` §1 and §4 re-measured against main `0a4a366d` (after #149's fan-out, F1, F2 and F3). Measured with the repository's venv (Python 3.14.7, httpx 0.28.1) and `helm template`. No lab read; §5 states the walk. §7's 27 blocks were generated from a working copy and proved against a clean checkout of `0a4a366d` (§4.3) |

## How to read this spec

The plain point first: a scheduled report lands in the artefact store and nobody is told. This spec lets a schedule
name a webhook. When the schedule's Job sees a run finish, it POSTs that run's facts (which report, which cluster,
the run id, its sha256, when it finished, its sizes) to the webhook. The webhook URL is a secret (a Slack or Teams
URL carries its key in its path), so it lives in a Kubernetes Secret mounted as a file, and nothing the Job prints
ever contains it.

§1 is the mandate. §2 is the research: sources, the code, the probes. §2a weighs the alternatives. §3 is the
design, one rule per subsection with its reason. §4 maps each Definition-of-Done item to a test and records the
proof. §5 is the walk on the lab. §6 is what an operator sees. §7 is the change as implementation blocks
(`docs/specs/README.md`, "Implementation blocks"), applied with

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_F4_webhook_delivery.md . --apply

Line citations into the code at `0a4a366d` are `file:line` in plain text inside quoted output and tables; prose
cites `path#anchor`.

## Orchestrator's notes

1. **The design doc predates #149, F1, F2 and F3** (§2.4 lists what no longer holds). Its status line gains one
   sentence pointing here (Block 26); `DESIGN_reporting_service.md` §5.6, which says "nothing is mailed", gains
   one sentence (Block 27).
2. **The issue's line numbers hold.** trigger.py:48-60 (the flags), :88-94 (the 409 skip), :98-127 (the fan-out
   wait), :120-121 (the per-run line); report-cronjob.yaml:32, :41, :42; report-networkpolicy.yaml:18 — all
   unchanged on `0a4a366d`.
3. **One CA recipe.** The dashboard builds `GSD_TRUSTED_CA_FILE` inline in deployment.yaml (`$ca` list). The Job
   needs the same list, so it moves into one helper, `gsd.trustedCaFile` (Blocks 10, 12), and both read it; the
   Python side reuses `gsd.config._trusted_ca_context`, the function `ClusterConfig.verify` already calls
   (config.py:558), not a copy. Both renders are byte-identical before the version blocks (§4.3).
4. **The lab walk needs a schedule that delivers.** `environments/crc.yaml` gains a fourth schedule,
   `delivery-walk`, suspended (`enabled: false`), so it never fires on its own and its absent Secret blocks
   nothing; the walk fires it with `oc create job --from` (§5). The CRC render therefore gains that one CronJob and
   the report pod's `GSD_REPORT_SCHEDULES` lists it (§4.3); the three existing CronJobs render unchanged.
5. **The index count.** Fifty-five on `0a4a366d`; this row makes it fifty-six, and
   `local-development/tests/test_specs_index.py` moves to 56. #109 is below the numbers of the rows above it, so F4
   is excluded from the rising-number assert by its id and pinned to #109, as F1, F2 and F3 were.
6. **Dates.** Blocks 24 and 25 date the history lines 2026-10-04; the implementing pull request writes its own.

Questions settled by the orchestrator (2026-10-03, on "easy to manage, best practice"; the operator may reopen any):

1. **Per run, not per fan-out: SETTLED (§3.1).** A ten-cluster schedule sends ten events. One event per occurrence is
   what CloudEvents describes, keeps the attachment's memory bounded, and does not wait on the slowest cluster. The
   per-fire alternative (§2a, B) stays written out there.
2. **Slack and Teams: SETTLED, a later `deliver.kind` (§2.1).** The event is generic JSON. A `kind: slack` (Block Kit
   `text`) or `kind: teams` (an Adaptive Card for a Workflows trigger) is a follow-up; neither is built here.
3. **A proxy: SETTLED, none (as for the dashboard).** The chart has no proxy setting for any workload (measured:
   `grep -niE 'https?_proxy|no_proxy|proxy:'` over `values.yaml` and the templates finds only the oauth-proxy), so
   the Job matches the rest of the chart. An estate whose egress must use a proxy needs a chart-wide setting, which
   is its own issue.

## 1. The mandate, and what is out of scope

The mandate (#109, "The change", "Must not change" and "Definition of Done"): choose the payload, per-run or
per-fan-out delivery, the retry and whether a delivery failure fails the Job; build `reporting.schedules[].deliver`
(`kind: none|webhook`, `webhookUrlSecret`, `attach: none|html|pdf|csv`) rendered into the CronJob only when `kind`
is not `none`, the URL from a Secret mounted read-only, never in argv, never logged; document egress in the chart
README; keep the report service free of outbound calls, the 409 skip at exit 0 with nothing delivered, exit 1
when any run failed, and `backoffLimit: 0`.

Out of scope: SMTP and object stores (later `deliver.kind` values), a Slack- or Teams-shaped payload (open
question 2), delivery of manual runs (delivery is a property of a schedule, design §4), a re-send command.

## 2. Research, measured

### 2.1 Primary sources

| Source | What it says | What this spec takes |
|---|---|---|
| CloudEvents 1.0.2, `cloudevents/spec.md`, "REQUIRED Attributes" | `id`, `source`, `specversion`, `type` are required; "Producers MUST ensure that `source` + `id` is unique for each distinct event. If a duplicate event is re-sent (e.g. due to a network error) it MAY have the same `id`. Consumers MAY assume that Events with identical `source` and `id` are duplicates." | `id` is the run id, `source` the report Service URL: a retried POST is recognisable as the same event |
| CloudEvents 1.0.2, `formats/json-format.md` §3 and §3.1.1 | structured mode "MUST use the media type `application/cloudevents+json`"; with a JSON `datacontenttype` "the `data` value MUST be stored directly as a JSON value" | the body is one JSON object, `data` a JSON object |
| CloudEvents 1.0.2, `bindings/http-protocol-binding.md` §3.2.1 | "The HTTP `Content-Type` header MUST be set to the media type of an event format", e.g. `application/cloudevents+json; charset=UTF-8` | the POST's Content-Type |
| Slack, "Sending messages using incoming webhooks" (docs.slack.dev) | payload is `text` and/or `blocks`; "Your webhook URL contains a secret. Don't share it online"; errors 400 `invalid_payload`/`no_text`, 403, 404, 410 `channel_is_archived`. Rate limits page: incoming webhooks "1 per second", over the limit "HTTP 429 Too Many Requests" with `Retry-After`. File upload is `files.getUploadURLExternal` + `files.completeUploadExternal` with a `files:write` token, not a webhook | the URL is a secret; 429 + `Retry-After` is honoured; a Slack webhook rejects a body without `text` (`no_text`), so it needs an adapter (open question 2); no attachment can reach Slack through a webhook |
| Microsoft, "Retirement of Office 365 connectors within Microsoft Teams" (devblogs, update 2026-04-14) | connectors "progressively disabled … Rollout begins: May 18, 2026", completing May 22, 2026; move to Power Automate Workflows | on 2026-10-04 the Teams connector webhooks are gone |
| Microsoft Learn, "Create incoming webhooks with Workflows" (updated 2026-08-03) and the Teams connector reference "When a Teams webhook request is received" | the trigger takes `{"type":"message","attachments":[{"contentType":"application/vnd.microsoft.card.adaptive",…}]}` or a Message Card; "The message size limit is 28 KB"; throttled above four requests a second | Teams needs an Adaptive Card adapter (open question 2); 28 KB rules out an attachment there |
| RFC 9110 §10.2.3 | `Retry-After = HTTP-date / delay-seconds` | both forms parsed (`_retry_after`) |
| RFC 9110 §9.2.2 | PUT and DELETE are idempotent; POST is not | a retried POST may arrive twice; the CloudEvents `id` lets the receiver drop it |
| Google Cloud Storage, "Retry strategy" | retry "HTTP `408`, `429`, and `5xx` response codes"; "use exponential backoff with jitter" | `RETRYABLE_STATUSES` = 408, 429, 500, 502, 503, 504 |
| AWS Architecture Blog, "Exponential Backoff And Jitter" (Brooker, 2015) | full jitter: `sleep = random_between(0, min(cap, base * 2 ** attempt))` | `_deliver`'s delay, base 2 s, cap 30 s |
| httpx 0.28.1 `_config.py` `create_ssl_context` | `verify=True` uses `SSL_CERT_FILE`/`SSL_CERT_DIR` when set, else certifi | the Job passes an `SSLContext` built from the chart's bundles, the dashboard's way |
| httpx 0.28.1 `_models.py` `Response.raise_for_status` | the message is `"… for url '{url}'"` | measured in §2.3: it leaks the URL |

### 2.2 The code, read on `0a4a366d`

| Fact | Where |
|---|---|
| The trigger's flags are `--url` to `--timeout`; no delivery | local-development/gsd/reporting/trigger.py:47-60 |
| A 409 prints `{"skipped": …}` and returns 0 before any run exists | trigger.py:88-94 |
| The fan-out waits on a `pending` map, prints one line per finished run (`id, cluster, status, sha256, bytes, error`), exits 1 if any failed or the wait timed out | trigger.py:98-127 |
| A run record (`GET /report/api/runs/{id}`) is `Run.public()`: `id, report, cluster, params, formats, generated_by, generated_by_note, schedule, requested_at, status, started_at, finished_at, error, sha256, snapshot_stamp, bytes, pdf_variant, render_seconds, origin` plus `expires_at`, `retained_by` | local-development/gsd/reporting/artifacts.py:40-66, server.py:604-610 |
| The report's own `generated_at` is in the `.json`, not the run record; the record's `finished_at` is stamped when the render ends | runs.py:207-210 |
| The artefact endpoint answers 404 until `done`, and names its media type | server.py:612-633 |
| The Job: `concurrencyPolicy: Forbid`, `backoffLimit: 0`, `activeDeadlineSeconds: 900`, the wait `--timeout 840`, memory limit 128Mi | templates/report-cronjob.yaml:32, :41, :42, :81, :114 |
| The only chart NetworkPolicy for reporting selects the report pod and is `policyTypes: [Ingress]`; nothing selects the Job's pods | templates/report-networkpolicy.yaml:16-18 |
| The dashboard's CA trust: `GSD_TRUSTED_CA_FILE` from `trustedCA.injected` (an OpenShift-injected bundle, on by default) and `trustedCA.existingConfigMap`; read by `_trusted_ca_context`, which loads each over OpenSSL's default store | templates/deployment.yaml:279-290, values.yaml:924-946, gsd/config.py:83-138 |
| No module under `gsd/reporting/` other than trigger.py imports an HTTP client (`grep -rln "httpx\|requests\|urllib.request\|http.client\|socket"` finds trigger.py and a comment in `__init__.py`) | §4, T109-9 |

### 2.3 The probes

`str()` of httpx's exceptions, measured on httpx 0.28.1 with a URL whose path holds `SECRETPART`:

    HTTPStatusError str: "Server error '500 Internal Server Error' for url 'https://hooks.example.invalid/services/T000/B000/SECRETPART'\nFor more information check: …"
      contains SECRETPART: True
    Request repr: <Request('POST', 'https://hooks.example.invalid/services/T000/B000/SECRETPART')> True
    Response repr: <Response [500 Internal Server Error]> False
    ConnectError str: '[Errno 61] Connection refused' | SECRETPART in str: False | in repr: False | e.request.url has it: True
    ConnectError str: '[Errno 8] nodename nor servname provided, or not known' | SECRETPART in str: False
    ConnectTimeout str: 'timed out' | SECRETPART in str: False
    ConnectError "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: IP address mismatch, certificate is not valid for '140.82.114.4'. (_ssl.c:1082)" | host in str: True
    UnsupportedProtocol "Request URL has an unsupported protocol 'ftp://'." | SECRETPART: False

So `HTTPStatusError` and a `Request`'s repr carry the whole URL, and a TLS `ConnectError` carries the host. The
rule (§3.4) prints the status code or the exception's class, never `str()` or `repr()` of either, and never
calls `raise_for_status()`.

### 2.4 What `DESIGN_reporting_output_and_delivery.md` §1 and §4 say that no longer holds

- §1: "`formats ⊆ {html,pdf}`" and "`--cluster …`" on the CronJob: F2 added `csv`, #149 made the schedule
  cluster-agnostic (trigger.py:50, report-cronjob.yaml:71-74).
- §4: "a generic URL, which covers Slack/Teams incoming webhooks": a Slack webhook refuses a body without `text`,
  and Teams' Office 365 connectors were disabled in May 2026 (§2.1). The generic event needs an adapter for both.
- §4.2: `"generated_at": run.get("started_at")`: the run record's honest instant is `finished_at`; the report's
  `generated_at` is inside the `.json` (§2.2). The payload names `finished_at`.
- §4.2: "a link": the only artefact URL the Job knows is the internal Service, which needs the service token; a
  link is useless to the receiver, so none is sent (§3.2).
- §4.2: `resp.raise_for_status()`: its exception quotes the URL (§2.3).
- §4 round 1: "matching the existing report-pod comment that its egress policy is documentation": no chart
  template or README line mentions egress on `0a4a366d` (`grep -rni egress charts/group-sync-dashboard/{templates,README.md,values.yaml}` finds none). The README paragraph is new (Block 19).
- §4 round 1: "the poll loop is refactored so the run id and status are in scope": #220 did it (trigger.py:117-123).

## 2a. Alternatives considered

| | Option | Taken? | Why |
|---|---|---|---|
| A | One event per finished run, sent as it finishes | **yes** | one occurrence per event (CloudEvents `id` = run id); memory bounded to one attachment in a 128Mi Job; no wait on the slowest cluster |
| B | One event per fan-out, after the last run | no | one message per fire, but N attachments in one body (memory and receiver limits), and one failed cluster's facts wait for the slowest render |
| C | Plain JSON of the facts, no envelope | no | six fewer short fields, but no standard dedupe key or type for a retried POST; a plain JSON receiver parses the CloudEvent as plain JSON anyway |
| D | Slack `text` / Teams Adaptive Card | no (open question 2) | each is one vendor's shape; the generic event is the base a `kind` adapter can wrap |
| E | Multipart upload of the artefact | no | no named receiver accepts it (Slack and Teams take no file through a webhook, §2.1); base64 in JSON keeps one content type |
| F | A link to the artefact | no | the Job knows only the internal Service URL, which needs the service token (§2.4) |
| G | Delivery failure exits 0 | no | an undelivered report then fails silently, which is the issue's problem; see §3.3 |

## 3. The design

### 3.1 One event per finished run

Inside the existing wait loop (trigger.py:117-123), each run that reaches `done` or `failed` is delivered at once.
A failed run is delivered too: its `status` and `error` tell the receiver evidence is missing. Why per run: §2a A.

### 3.2 The payload, exactly

`POST <url>` with `Content-Type: application/cloudevents+json; charset=utf-8`:

```json
{"specversion": "1.0",
 "id": "20261004T030000.123456Z-1a2b",
 "source": "https://group-sync-dashboard-report.group-sync-dashboard.svc:8443",
 "type": "io.github.ephico2real2.gsd.report.run.finished",
 "time": "2026-10-04T03:00:07Z",
 "datacontenttype": "application/json",
 "data": {"report": "groups", "cluster": "crc-local", "run_id": "20261004T030000.123456Z-1a2b",
          "status": "done", "schedule": "weekly-groups",
          "sha256": "<64 hex>", "finished_at": "2026-10-04T03:00:07Z",
          "bytes": {"json": 41233, "html": 88120}, "error": null}}
```

The facts are the run record's own fields (§2.2); nothing is read from the artefact. `source` is the report
Service URL the Job already holds (`--url`), so `source` + `id` is unique across releases. With
`attach: html|pdf|csv`, a `done` run's `data` gains

```json
"attachment": {"format": "html", "media_type": "text/html; charset=utf-8", "bytes": 88120, "content_base64": "…"}
```

or, when it cannot be sent, `{"format": "pdf", "omitted": "this run stored no pdf"}` (or the size over the cap, or
the artefact read's status). Why base64 in the JSON: one content type for every receiver; the CloudEvent stays one
document. The cap, `ATTACH_MAX_BYTES` = 5 MiB: the Job holds the attachment about four times (bytes, base64, the
body, the request) under its 128Mi limit (report-cronjob.yaml:114); a larger artefact is named, never truncated.
A receiver that cannot take a large body (Teams: 28 KB, §2.1) uses `attach: none`.

### 3.3 Retry, and the exit rule

- Retried: any `httpx.TransportError` (the POST may not have arrived) and 408, 429, 500, 502, 503, 504.
  Not retried: every other status (a 400, 401, 403, 404 or 410 is a configuration fault a retry cannot fix) and a
  3xx (redirects are not followed, so a moved URL is a failure, not a POST to somewhere else).
- `DELIVER_ATTEMPTS` = 4, each with a 10 s timeout. The delay is the receiver's `Retry-After` (seconds or an
  HTTP-date, capped at 60 s) or full jitter, `uniform(0, min(30, 2 × 2^(attempt−1)))`. A retry that could not
  finish before the wait's own deadline (`--timeout 840`, inside `activeDeadlineSeconds: 900`) is not started.
  Worst case per run with no Retry-After: 4 × 10 s + 3 × 30 s = 130 s, spent inside the wait's 840 s; only an
  attempt already in flight can run past 840 s, into the 60 s the chart leaves before 900.
- **A run not delivered fails the Job (exit 1)**: the issue's original rule, confirmed. Why: once a schedule
  names a receiver, the delivery is the schedule's purpose; an exit 0 would make the failure invisible, which is
  exactly the problem #109 exists for. `kube_job_status_failed` fires as it does for a failed run, and the Job's
  log says which: `delivery failed for run <id>: HTTP 404 after 1 attempt(s)` against a run line with
  `"status": "done"`. No duplicate render follows: `backoffLimit: 0` stays, and every other run is still
  delivered before the exit.

### 3.4 The URL is never printed

The URL is read from `--webhook-url-file` (the Secret's key mounted as `/etc/gsd/deliver/url`), checked to be an
http(s) URL with a host, and passed only to `hook.post`. Every message about it names the HTTP status
(`HTTP 503`) or the exception's class (`ConnectError`), never `str(exc)`, `repr(request)` or the URL (§2.3). A
missing file, a bad scheme or `--deliver` without `--wait` is refused before any run is requested, so a schedule
that cannot deliver renders nothing. The receiver gets its own client: it never sees the service token.

### 3.5 TLS: the dashboard's trust

An https receiver is verified with `_trusted_ca_context() or True`, the expression `ClusterConfig.verify` uses
(config.py:558): the chart's injected bundle (system trust plus `proxy/cluster.spec.trustedCA`, on by default) and
`trustedCA.existingConfigMap` when set, else httpx's certifi. The delivering CronJob mounts the same ConfigMaps
and gets `GSD_TRUSTED_CA_FILE` from `gsd.trustedCaFile`, the one helper the dashboard now reads too. An operator
adds an enterprise CA the way the dashboard already documents it: `trustedCA.existingConfigMap`.

### 3.6 The chart

```yaml
reporting:
  schedules:
    - name: weekly-groups
      schedule: "0 23 * * 0"
      report: groups
      deliver:
        kind: webhook                                # none (default) | webhook
        webhookUrlSecret: {name: team-hook, key: url} # key defaults to url
        attach: html                                 # none (default) | html | pdf | csv
```

Rendered only when `kind` is not `none`: the args `--deliver webhook --webhook-url-file /etc/gsd/deliver/url
[--attach <fmt>]`, the Secret's one key as the file `url` (0440, read-only), and the trust mounts and env.
Refused at render: an unknown `kind` or `attach`; `webhook` without `webhookUrlSecret.name`; `attach` without
`webhook`; an `attach` format the schedule does not store (its `formats`, else `reporting.formats.scheduled`).
`gsd.reportSchedulesJson` (the status page's list) is unchanged: like `params` and `formats`, delivery is the
CronJob's business.

### 3.7 Egress: no NetworkPolicy, documented

Re-checked: nothing in the chart selects the Job's pods (§2.2), so their egress is open wherever the namespace has
no default-deny policy of its own. Where it has one, today's Job already needs DNS and the report Service; the
receiver joins them. The chart cannot render that rule: a NetworkPolicy matches CIDRs and ports, never a
hostname, and the hostname sits in a Secret the render never reads. The README says so and names OVN-Kubernetes'
`EgressFirewall` `dnsName` rule as the hostname-based control (Block 19).

### 3.8 What does not change, and the test that holds it

| Must not change | Held by |
|---|---|
| A schedule without `deliver` renders today's CronJob | §4.3's `helm template` diffs (default and CRC, byte-identical before the version blocks); T109-10 (`kind: none` equals no block) |
| The report service makes no outbound call | T109-9 (no module but trigger.py imports an HTTP or mail client, none imports the trigger) |
| A 409 is exit 0 with nothing delivered | T109-7; `test_p2_selectors.py::TestTriggerWindow` unchanged |
| Exit 1 when any run failed | T109-6; `test_p2_selectors.py` fan-out test unchanged |
| `backoffLimit: 0` | T109-10; `test_chart_reporting.py::test_a_schedule_renders_one_cronjob_with_the_trigger_command` unchanged |
| RBAC | §4.3: rendered atoms REMOVED 0, ADDED 0 |

### 3.9 Safety budget

The one new network posture is the Job's POST to a URL the operator names, from a pod that holds only the report
service token (never sent to the receiver) and the run's facts. The report pod, its Service, its NetworkPolicy and
its RBAC are untouched.

## 4. Tests

### 4.1 One test per Definition-of-Done item

| DoD item | Test |
|---|---|
| `--deliver webhook` posts the facts of each finished run to a fake receiver | T109-1 (`test_report_delivery.py`), T109-2 (`--attach`) |
| a failed POST follows the retry and exit rule and prints the status code but no part of the URL | T109-3 (503 + Retry-After, retried), T109-4 (404 not retried, exit 1), T109-5 (transport error: class only), T109-8 (refusals before any request) |
| a skipped (409) run delivers nothing | T109-7 |
| `helm template` renders the deliver args and the Secret mount only when `deliver.kind` is not `none` | T109-10, T109-11 (`test_chart_reporting.py::TestScheduleDelivery`) |
| Must not change | T109-6, T109-9, T109-10, §4.3 |

### 4.2 Each test fails without the change, and why

On `0a4a366d` with only the two test files copied in: T109-1 to T109-8 fail with
`gsd.reporting.trigger: error: unrecognized arguments: --deliver webhook --webhook-url-file …`; T109-10 fails
because no `--deliver` reaches the command, T109-11 because no render is refused. T109-9 passes before and after:
it is the "Must not change" guard, written to fail if a later change gives the service a client.

    10 failed, 1 passed in 0.99s

### 4.3 The proof

Every command below ran on 2026-10-04 against a detached worktree of origin/main `0a4a366d` with this spec
committed into it, using the repository's venv (`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.` from
`local-development`) and helm on PATH. The worktree was removed afterwards.

**The blocks.**

    $ python local-development/apply-spec-blocks.py docs/specs/SPEC_F4_webhook_delivery.md .
    27 blocks check out across 15 files
    $ python local-development/apply-spec-blocks.py docs/specs/SPEC_F4_webhook_delivery.md . --apply
    27 blocks check out across 15 files
    applied to …/base

The applied tree is byte-equal, file by file, to the working copy the blocks were generated from.

**The new tests fail on main** (the two test files copied onto a clean `0a4a366d`):

    $ pytest -q tests/test_report_delivery.py "tests/test_chart_reporting.py::TestScheduleDelivery"
    FAILED tests/test_report_delivery.py::test_t109_1_… (… T109-8: unrecognized arguments: --deliver webhook --webhook-url-file …)
    FAILED tests/test_chart_reporting.py::TestScheduleDelivery::test_t109_10_…
    FAILED tests/test_chart_reporting.py::TestScheduleDelivery::test_t109_11_…
    10 failed, 1 passed in 0.99s

The one pass is T109-9, the no-outbound guard (§4.2).

**The suites on the applied tree:**

    $ pytest -q tests/test_report_delivery.py tests/test_reporting_*.py tests/test_chart_*.py tests/test_report_*.py \
        tests/test_specs_index.py tests/test_docs_citations.py tests/test_kyverno.py tests/test_release_crc.py \
        tests/test_crc_schedules_in_window.py tests/test_p2_selectors.py tests/test_values_defaults.py tests/test_config.py
    3073 passed, 21 skipped, 2 warnings in 185.09s (0:03:05)

**`helm template`, the chart's blocks alone** (Blocks 10 to 18 applied, before the version blocks moved the
labels), release `t` for the defaults and `group-sync-dashboard` with main's `environments/crc.yaml`:

    default values: base chart vs applied chart: byte-identical (4177 lines)
    crc.yaml of main: base chart vs applied chart: byte-identical (4582 lines, 4 CronJobs)
    trustedCA.existingConfigMap.enabled=true, trustedCA.injected.enabled=false: identical

**`helm template`, every block applied.** Default values and main's `crc.yaml`: the only lines that differ are
`helm.sh/chart` (0.66.7 → 0.67.0, 43 and 48 lines), `app.kubernetes.io/version` and the two image tags (4.3.0 →
4.4.0), and two values computed from those labels on every bump: `checksum/config` (2 lines) and the offsite
RoleBinding's hashed name (1 line). The applied `crc.yaml` against main's, on the applied chart: one CronJob added
(`group-sync-dashboard-report-delivery-walk`, suspended, 141 lines) and two lines changed on the report
Deployment (`checksum/reporting`, and `GSD_REPORT_SCHEDULES` naming the fourth schedule); the three existing
CronJobs unchanged.

**RBAC**, every Role, ClusterRole and binding rendered as atoms (kind, role, apiGroup, resource, verb, names;
binding subjects):

    default: RBAC atoms 64 -> 64; REMOVED 0, ADDED 0
    crc: RBAC atoms 71 -> 71; REMOVED 0, ADDED 0
    crc applied crc.yaml: RBAC atoms 71 -> 71; REMOVED 0, ADDED 0

**Not measured:** the lab (§5): the report image mounting `/etc/pki/ca-trust/extracted/pem/injected` read-only
(the dashboard image, of the same base, does it today), the receiver, the logs; the full hermetic and browser
suites (the implementing pull request runs them).

## 5. On the lab (the implementing pull request)

After the release is deployed with `release-crc.sh --argocd` (the data and report-artifacts PVC UIDs recorded
before and after), inside the reporting window (22:00–06:00 America/New_York, environments/crc.yaml:81-86),
in namespace `group-sync-dashboard`:

1. **The receiver.** A Pod and Service named `gsd-delivery-walk`, labelled `app=gsd-delivery-walk`, on the report
   image already on the node (no new pull, no egress), running `python3.14 -c` with a stdlib `http.server`
   handler on port 8080 that answers 200 to a POST and prints one line per request to stdout:
   `{"path_len": <n>, "content_type": "...", "body": <the JSON it received>}` — the path's length, never the
   path, so the receiver's own log cannot hold the URL's secret part. Nothing selects it in a NetworkPolicy, so
   the Job reaches it.
2. **The Secret.** `oc create secret generic gsd-delivery-walk --from-literal=url=http://gsd-delivery-walk.group-sync-dashboard.svc:8080/hook/<32 random hex>`;
   the random part is the marker searched for in step 4.
3. **The fire.** `oc create job delivery-walk-1 --from=cronjob/group-sync-dashboard-report-delivery-walk`, then
   wait for the Job's completion (one waiter, not a poll).
4. **The checks.** `oc logs job/delivery-walk-1`: one `"delivered"` line per fanned-out cluster, exit 0; the
   receiver's log: one event per cluster, each `data` matching that run's line (id, cluster, status, sha256,
   bytes) and an `attachment` whose base64 decodes to the html artefact (sha256 of the bytes equal to
   `GET /report/api/runs/<id>/artifact?format=html`); `oc logs job/delivery-walk-1 | grep -c <marker>` is 0, and
   so is a grep for `gsd-delivery-walk.group-sync-dashboard.svc` and `/hook/`; `oc get job delivery-walk-1 -o
   yaml | grep -c <marker>` is 0 (the URL is in no pod spec).
5. **The failure path.** Delete the receiver Pod only, fire `delivery-walk-2`: the Job fails, its log names
   `ConnectError` (or `ConnectTimeout`) with no part of the URL, and the runs are still `done` on the Report history.
6. **Removal.** `oc delete pod,service,secret -l app=gsd-delivery-walk` (the Secret is created with
   `oc label secret gsd-delivery-walk app=gsd-delivery-walk` after step 2) and `oc delete job delivery-walk-1
   delivery-walk-2`; `oc get all,secret -l app=gsd-delivery-walk` answers nothing. The CronJob stays suspended.

The evidence (the Job logs, the receiver's lines with the base64 bodies cut to their length, the greps) is
committed under `reports/<date>_109-webhook-delivery/` and posted on #109 pinned to the merge sha.

## 6. What an operator sees, and what it costs

A schedule with `deliver` posts one event per cluster per fire; the Job's log gains one `{"delivered": …}` line
per run and, on trouble, a stderr line naming the run, the status or the exception's class, and the attempts. A
delivery that keeps failing turns the Job red like a failed run. Cost: one Secret per receiver, the Job's egress
to it, and with `attach` up to 5 MiB more memory in the Job per run. No new image, permission, migration or
route.

## 7. Implementation blocks

### Block 1 — `local-development/gsd/reporting/trigger.py`: the docstring names delivery

<!-- block: local-development/gsd/reporting/trigger.py | edit -->

```python
the run's status and kube_job_status_failed can alert on it.
"""
```

```python
the run's status and kube_job_status_failed can alert on it.

With --deliver webhook (#109, docs/specs/SPEC_F4_webhook_delivery.md) each finished run's facts are POSTed,
as one CloudEvent, to the URL in --webhook-url-file (a mounted Secret). The URL is never printed: a failed
delivery names the HTTP status or the exception's class, and an undelivered run exits 1 like a failed one.
"""
```

### Block 2 — `local-development/gsd/reporting/trigger.py`: the imports

<!-- block: local-development/gsd/reporting/trigger.py | edit -->

```python
import argparse
import json
import os
import sys
import time

import httpx

```

```python
import argparse
import base64
import contextlib
import json
import os
import random
import ssl
import sys
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

from ..config import ConfigError, _trusted_ca_context

```

### Block 3 — `local-development/gsd/reporting/trigger.py`: delivery: the constants, the URL file, Retry-After, the attachment, the event, the POST with its retry

<!-- block: local-development/gsd/reporting/trigger.py | edit -->

```python

def main(argv: list[str] | None = None) -> int:
```

```python

#: Delivery (#109). Retried: a POST that may not have arrived (any transport error) and an answer that says
#: "try again" (RFC 9110 §15.5.9 408, §15.6 5xx, RFC 6585 429). A retried POST can arrive twice; the event's
#: `id` is the run id, so the receiver drops the second copy (CloudEvents 1.0 §3.1.1 `id`).
DELIVER_ATTEMPTS = 4
DELIVER_TIMEOUT_SECONDS = 10.0
DELIVER_BACKOFF_BASE_SECONDS, DELIVER_BACKOFF_CAP_SECONDS = 2.0, 30.0
RETRY_AFTER_CAP_SECONDS = 60.0
RETRYABLE_STATUSES = frozenset({408, 429, 500, 502, 503, 504})
#: An attachment rides base64 in the JSON, so the Job holds it about four times over (bytes, base64, the
#: body, the encoded request) under its 128Mi limit; a larger artefact is named, not sent.
ATTACH_MAX_BYTES = 5 * 1024 * 1024
EVENT_TYPE = "io.github.ephico2real2.gsd.report.run.finished"


def _webhook_url(path: str) -> str | None:
    """The URL from the mounted Secret, or None after saying why. The reason never quotes the URL."""
    try:
        with open(path, encoding="utf-8") as fh:
            raw = fh.read().strip()
    except OSError as exc:
        print(f"--webhook-url-file cannot be read ({type(exc).__name__})", file=sys.stderr)
        return None
    try:
        url = httpx.URL(raw)
    except httpx.InvalidURL:
        url = None
    if url is None or url.scheme not in ("http", "https") or not url.host:
        print("--webhook-url-file does not hold an http(s) URL", file=sys.stderr)
        return None
    return raw


def _retry_after(r: httpx.Response) -> float | None:
    """RFC 9110 §10.2.3: delay-seconds or an HTTP-date; capped, and None when absent or unreadable."""
    raw = r.headers.get("Retry-After", "").strip()
    if not raw:
        return None
    if raw.isdigit():
        seconds = float(raw)
    else:
        try:
            seconds = (parsedate_to_datetime(raw) - datetime.now(UTC)).total_seconds()
        except (TypeError, ValueError):
            return None
    return min(max(seconds, 0.0), RETRY_AFTER_CAP_SECONDS)


def _attachment(service: httpx.Client, run: dict, fmt: str) -> dict:
    """The artefact itself, base64, or the reason it is not sent. Only a `done` run has artefacts."""
    size = (run.get("bytes") or {}).get(fmt)
    if size is None:
        return {"format": fmt, "omitted": f"this run stored no {fmt}"}
    if size > ATTACH_MAX_BYTES:
        return {"format": fmt, "omitted": f"{size} bytes is over the {ATTACH_MAX_BYTES}-byte cap"}
    r = service.get(f"/report/api/runs/{run['id']}/artifact", params={"format": fmt})
    if r.status_code != 200:
        return {"format": fmt, "omitted": f"the artefact read answered {r.status_code}"}
    return {"format": fmt, "media_type": r.headers.get("content-type"), "bytes": len(r.content),
            "content_base64": base64.b64encode(r.content).decode("ascii")}


def _event(run: dict, schedule: str, source: str, attachment: dict | None) -> dict:
    """One finished run as a CloudEvents 1.0 structured-mode event: the run's facts in `data`."""
    data = {"report": run.get("report"), "cluster": run.get("cluster"), "run_id": run["id"],
            "status": run["status"], "schedule": schedule, "sha256": run.get("sha256"),
            "finished_at": run.get("finished_at"), "bytes": run.get("bytes") or {}, "error": run.get("error")}
    if attachment is not None:
        data["attachment"] = attachment
    return {"specversion": "1.0", "id": run["id"], "source": source, "type": EVENT_TYPE,
            "time": run.get("finished_at"), "datacontenttype": "application/json", "data": data}


def _deliver(hook: httpx.Client, url: str, event: dict, deadline: float) -> bool:
    """POST the event, retrying what may succeed later with full-jitter backoff (or the receiver's
    Retry-After) while the Job's deadline allows. Prints the status or the exception's CLASS, never str():
    httpx's HTTPStatusError and a TLS ConnectError quote the URL or its host (SPEC_F4 §2.3)."""
    run_id = event["id"]
    body = json.dumps(event).encode("utf-8")
    headers = {"Content-Type": "application/cloudevents+json; charset=utf-8"}
    for attempt in range(1, DELIVER_ATTEMPTS + 1):
        try:
            r = hook.post(url, content=body, headers=headers)
        except httpx.HTTPError as exc:
            outcome, retry, wait = type(exc).__name__, isinstance(exc, httpx.TransportError), None
        else:
            if 200 <= r.status_code < 300:
                print(json.dumps({"delivered": run_id, "http_status": r.status_code, "attempts": attempt}))
                return True
            outcome, retry, wait = f"HTTP {r.status_code}", r.status_code in RETRYABLE_STATUSES, _retry_after(r)
        delay = wait if wait is not None else random.uniform(
            0, min(DELIVER_BACKOFF_CAP_SECONDS, DELIVER_BACKOFF_BASE_SECONDS * 2 ** (attempt - 1)))
        if not retry or attempt == DELIVER_ATTEMPTS or time.monotonic() + delay + DELIVER_TIMEOUT_SECONDS > deadline:
            print(f"delivery failed for run {run_id}: {outcome} after {attempt} attempt(s)", file=sys.stderr)
            return False
        print(f"delivery of run {run_id}: {outcome}; retrying in {delay:.1f}s ({attempt}/{DELIVER_ATTEMPTS})",
              file=sys.stderr)
        time.sleep(delay)
    return False


def main(argv: list[str] | None = None) -> int:
```

### Block 4 — `local-development/gsd/reporting/trigger.py`: the three flags, checked before any run is requested

<!-- block: local-development/gsd/reporting/trigger.py | edit -->

```python
    ap.add_argument("--timeout", type=int, default=600)
    a = ap.parse_args(argv)
    params: dict = {}
```

```python
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--deliver", default="none", choices=["none", "webhook"],
                    help="send each finished run's facts to a webhook (needs --wait and --webhook-url-file)")
    ap.add_argument("--webhook-url-file", default="", help="a file holding the webhook URL (a mounted Secret)")
    ap.add_argument("--attach", default="none", choices=["none", "html", "pdf", "csv"],
                    help="send this artefact of a done run inside the event, base64, up to ATTACH_MAX_BYTES")
    a = ap.parse_args(argv)
    hook_url = None
    if a.deliver == "webhook":
        # Checked before the run is requested: a schedule that cannot deliver renders nothing.
        if not a.wait:
            print("--deliver webhook needs --wait: a run is delivered once it finishes", file=sys.stderr)
            return 1
        hook_url = _webhook_url(a.webhook_url_file)
        if hook_url is None:
            return 1
    params: dict = {}
```

### Block 5 — `local-development/gsd/reporting/trigger.py`: the receiver's own client and trust

<!-- block: local-development/gsd/reporting/trigger.py | edit -->

```python

    with httpx.Client(base_url=a.url, headers=headers, verify=verify, timeout=30.0) as c:
        r = _post(c, body)
```

```python

    hook_verify: ssl.SSLContext | bool = True
    if hook_url is not None:
        try:
            # The dashboard's trust: the chart's injected and enterprise bundles, else httpx's own (certifi).
            hook_verify = _trusted_ca_context() or True
        except ConfigError as exc:
            print(f"cannot load the trusted CA bundle: {exc}", file=sys.stderr)
            return 1
    # The webhook has its own client: the receiver never sees the service token, and a redirect is not followed.
    hook_client = (httpx.Client(verify=hook_verify, timeout=DELIVER_TIMEOUT_SECONDS, follow_redirects=False)
                   if hook_url is not None else contextlib.nullcontext())

    with httpx.Client(base_url=a.url, headers=headers, verify=verify, timeout=30.0) as c, hook_client as hook:
        r = _post(c, body)
```

### Block 6 — `local-development/gsd/reporting/trigger.py`: the undelivered count

<!-- block: local-development/gsd/reporting/trigger.py | edit -->

```python
        deadline = time.monotonic() + a.timeout
        failed = 0
        while pending and time.monotonic() < deadline:
```

```python
        deadline = time.monotonic() + a.timeout
        failed = undelivered = 0
        while pending and time.monotonic() < deadline:
```

### Block 7 — `local-development/gsd/reporting/trigger.py`: each finished run is delivered; an undelivered run fails the Job

<!-- block: local-development/gsd/reporting/trigger.py | edit -->

```python
                    del pending[run_id]
        if pending:
            print(f"timed out waiting for {len(pending)} run(s): {', '.join(sorted(pending))}", file=sys.stderr)
            return 1
    return 1 if failed else 0

```

```python
                    del pending[run_id]
                    if hook is not None:
                        attached = _attachment(c, run, a.attach) if a.attach != "none" and run["status"] == "done" else None
                        undelivered += not _deliver(hook, hook_url, _event(run, a.schedule, a.url, attached), deadline)
        if pending:
            print(f"timed out waiting for {len(pending)} run(s): {', '.join(sorted(pending))}", file=sys.stderr)
            return 1
    return 1 if failed or undelivered else 0

```

### Block 8 — `local-development/tests/test_report_delivery.py`: the trigger's tests, T109-1 to T109-9

<!-- block: local-development/tests/test_report_delivery.py | create -->

```python
"""#109 (docs/specs/SPEC_F4_webhook_delivery.md): the schedule Job delivers each finished run to a webhook.

The trigger is driven end to end with real httpx clients over one MockTransport that plays both the report
service and the receiver, so a status code, a Retry-After header and a transport error behave as httpx makes
them behave. The webhook URL carries a marker that must never reach stdout or stderr.
"""

from __future__ import annotations

import ast
import base64
import json
from pathlib import Path

import httpx
import pytest

from gsd.reporting import trigger

SERVICE = "https://svc.test:8443"
SECRET_PART = "T0SECRET/B0SECRET/xoxSECRETPATH"
HOOK = f"https://hooks.receiver.test/services/{SECRET_PART}"
REPORTING = Path(__file__).resolve().parents[1] / "gsd" / "reporting"


class _Lab:
    """The report service (a fan-out of two runs) and the receiver, behind one transport."""

    def __init__(self, hook_answers=None, create_status=202, run_status=None):
        self.hook_answers = list(hook_answers or [httpx.Response(200)])
        self.create_status = create_status
        self.run_status = run_status or {"r-crc": "done", "r-east": "done"}
        self.events: list[dict] = []
        self.hook_headers: list[httpx.Headers] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "hooks.receiver.test":
            self.hook_headers.append(request.headers)
            self.events.append(json.loads(request.content))
            answer = self.hook_answers.pop(0) if len(self.hook_answers) > 1 else self.hook_answers[0]
            if isinstance(answer, Exception):
                raise answer
            return answer
        assert "authorization" in request.headers, "the service is always called with the token"
        path = request.url.path
        if request.method == "POST" and path == "/report/api/runs":
            if self.create_status != 202:
                return httpx.Response(self.create_status, headers={"Retry-After": "3600"}, json={"detail": "closed"})
            return httpx.Response(202, json={"runs": [{"id": "r-crc", "cluster": "crc-local"},
                                                      {"id": "r-east", "cluster": "prod-east"}]})
        if path.endswith("/artifact"):
            return httpx.Response(200, content=b"<html>report</html>", headers={"content-type": "text/html; charset=utf-8"})
        run_id = path.rsplit("/", 1)[1]
        status = self.run_status[run_id]
        return httpx.Response(200, json={
            "id": run_id, "report": "groups", "cluster": {"r-crc": "crc-local", "r-east": "prod-east"}[run_id],
            "status": status, "sha256": "ab" * 32 if status == "done" else None,
            "finished_at": "2026-10-04T02:00:07Z", "bytes": {"json": 900, "html": 19} if status == "done" else {},
            "error": None if status == "done" else "render failed: KeyError"})


@pytest.fixture
def lab(monkeypatch, tmp_path):
    real = httpx.Client    # taken once: a second build in one test must not wrap the first one's patch

    def build(*extra: str, **kw):
        state = _Lab(**kw)

        def client(**options):
            options.pop("verify", None)    # the transport is the network; there is no TLS to verify
            return real(transport=httpx.MockTransport(state), **options)

        monkeypatch.setattr(trigger.httpx, "Client", client)
        monkeypatch.setattr(trigger.time, "sleep", lambda s: state.__dict__.setdefault("sleeps", []).append(s))
        token = tmp_path / "token"
        token.write_text("service-token")
        url_file = tmp_path / "url"
        url_file.write_text(HOOK + "\n")    # a Secret's value often ends in a newline
        argv = ["--url", SERVICE, "--report", "groups", "--schedule", "weekly", "--token-file", str(token),
                "--wait", "--deliver", "webhook", "--webhook-url-file", str(url_file), *extra]
        state.rc = trigger.main(argv)
        return state
    return build


def _no_url(out: str) -> None:
    for piece in (HOOK, "hooks.receiver.test", "T0SECRET", "xoxSECRETPATH"):
        assert piece not in out, f"the webhook URL leaked ({piece!r})"


def test_t109_1_each_finished_run_of_the_fan_out_is_delivered_as_one_event(lab, capsys):
    state = lab()
    out = capsys.readouterr()
    assert state.rc == 0, out.err
    assert [e["id"] for e in state.events] == ["r-crc", "r-east"]
    event = state.events[0]
    assert {k: event[k] for k in ("specversion", "type", "source", "time", "datacontenttype")} == {
        "specversion": "1.0", "type": trigger.EVENT_TYPE, "source": SERVICE,
        "time": "2026-10-04T02:00:07Z", "datacontenttype": "application/json"}
    assert event["data"] == {"report": "groups", "cluster": "crc-local", "run_id": "r-crc", "status": "done",
                             "schedule": "weekly", "sha256": "ab" * 32, "finished_at": "2026-10-04T02:00:07Z",
                             "bytes": {"json": 900, "html": 19}, "error": None}
    assert state.hook_headers[0]["content-type"] == "application/cloudevents+json; charset=utf-8"
    assert "authorization" not in state.hook_headers[0], "the receiver never sees the service token"
    assert out.out.count('"delivered"') == 2
    _no_url(out.out + out.err)


def test_t109_2_attach_sends_the_artefact_base64_and_names_what_it_cannot_send(lab, capsys):
    state = lab("--attach", "html")
    assert state.rc == 0
    attachment = state.events[0]["data"]["attachment"]
    assert base64.b64decode(attachment["content_base64"]) == b"<html>report</html>"
    assert attachment["media_type"] == "text/html; charset=utf-8" and attachment["bytes"] == 19
    state = lab("--attach", "pdf")
    assert state.events[0]["data"]["attachment"] == {"format": "pdf", "omitted": "this run stored no pdf"}


def test_t109_3_a_failed_post_retries_the_retryable_and_prints_the_status_never_the_url(lab, capsys):
    state = lab(hook_answers=[httpx.Response(503, headers={"Retry-After": "7"}), httpx.Response(200)])
    out = capsys.readouterr()
    assert state.rc == 0 and len(state.events) == 3, "r-crc took two attempts, r-east one"
    assert state.sleeps.count(7.0) == 1, "the receiver's Retry-After is honoured (the other sleeps are the 2 s polls)"
    assert "HTTP 503" in out.err
    _no_url(out.out + out.err)


def test_t109_4_an_undelivered_run_fails_the_job_and_a_4xx_is_not_retried(lab, capsys):
    state = lab(hook_answers=[httpx.Response(404)])
    out = capsys.readouterr()
    assert state.rc == 1, "a run that was not delivered fails the Job"
    assert len(state.events) == 2, "404 is not retried: one attempt per run"
    assert out.err.count("delivery failed for run") == 2 and "HTTP 404 after 1 attempt(s)" in out.err
    _no_url(out.out + out.err)


def test_t109_5_a_transport_error_is_retried_then_named_by_its_class_only(lab, capsys):
    # A TLS failure's str() names the host (SPEC_F4 §2.3): the class is all that is printed.
    tls = httpx.ConnectError("certificate is not valid for 'hooks.receiver.test'")
    state = lab(hook_answers=[tls])
    out = capsys.readouterr()
    assert state.rc == 1
    assert len(state.events) == 2 * trigger.DELIVER_ATTEMPTS
    assert f"ConnectError after {trigger.DELIVER_ATTEMPTS} attempt(s)" in out.err
    assert all(0 <= s <= trigger.DELIVER_BACKOFF_CAP_SECONDS for s in state.sleeps)
    _no_url(out.out + out.err)


def test_t109_6_a_failed_run_is_delivered_with_its_error_and_still_fails_the_job(lab, capsys):
    state = lab("--attach", "html", run_status={"r-crc": "done", "r-east": "failed"})
    assert state.rc == 1, "exit 1 when any run failed, delivered or not"
    failed = state.events[1]["data"]
    assert failed["status"] == "failed" and failed["error"] == "render failed: KeyError" and "attachment" not in failed


def test_t109_7_a_window_skip_delivers_nothing_and_exits_0(lab, capsys):
    state = lab(create_status=409)
    assert state.rc == 0 and state.events == []
    assert '"skipped"' in capsys.readouterr().out


def test_t109_8_a_bad_url_file_or_no_wait_is_refused_before_any_run_is_requested(monkeypatch, tmp_path, capsys):
    calls = []
    monkeypatch.setattr(trigger.httpx, "Client", lambda **kw: calls.append(kw))
    token = tmp_path / "token"
    token.write_text("t")
    base = ["--url", SERVICE, "--report", "groups", "--schedule", "weekly", "--token-file", str(token),
            "--deliver", "webhook"]
    assert trigger.main([*base, "--webhook-url-file", str(tmp_path / "absent"), "--wait"]) == 1
    bad = tmp_path / "bad"
    bad.write_text("ftp://hooks.receiver.test/" + SECRET_PART)
    assert trigger.main([*base, "--webhook-url-file", str(bad), "--wait"]) == 1
    good = tmp_path / "good"
    good.write_text(HOOK)
    assert trigger.main([*base, "--webhook-url-file", str(good)]) == 1, "delivery needs --wait"
    assert calls == [], "nothing was requested"
    _no_url(capsys.readouterr().err)


def test_t109_9_the_report_service_makes_no_outbound_call():
    """Delivery belongs to the schedule Job alone (DESIGN_reporting_output_and_delivery.md §4): no module the
    service runs imports an HTTP or mail client, and none imports the trigger."""
    clients = {"httpx", "requests", "urllib.request", "http.client", "socket", "smtplib", "aiohttp"}
    for path in sorted(REPORTING.rglob("*.py")):
        if path.name == "trigger.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(), str(path))):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                     else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            for name in names:
                assert name not in clients and not name.endswith("trigger"), (path.name, name)
```

### Block 9 — `local-development/tests/test_chart_reporting.py`: the chart's tests, T109-10 and T109-11

<!-- block: local-development/tests/test_chart_reporting.py | edit -->

```python
    assert "is not a boolean" in done.stderr
```

```python
    assert "is not a boolean" in done.stderr


class TestScheduleDelivery:
    """#109 (SPEC_F4): `deliver` renders the trigger's delivery args, the URL Secret and the trust bundles only
    when its kind is not none; the Job's run semantics are untouched."""

    BASE = ("reporting.schedules[0].name=weekly", "reporting.schedules[0].schedule=0 22 * * 0",
            "reporting.schedules[0].report=groups")
    NAME = "t-group-sync-dashboard-report-weekly"

    def _pod(self, *sets: str) -> dict:
        return _exact(_render(*self.BASE, *sets), "CronJob", self.NAME)["spec"]["jobTemplate"]["spec"]["template"]["spec"]

    def _refused(self, *sets: str) -> str:
        args = ["helm", "template", "t", str(CHART), "-n", "x", "--set", "ingress.host=h"]
        for s in (*self.BASE, *sets):
            args += ["--set", s]
        done = subprocess.run(args, capture_output=True, text=True, timeout=120)
        assert done.returncode != 0, "the render was not refused"
        return done.stderr

    def test_t109_10_a_webhook_renders_the_args_the_secret_and_the_trust_and_nothing_else_moves(self):
        plain = _exact(_render(*self.BASE), "CronJob", self.NAME)
        none = _exact(_render(*self.BASE, "reporting.schedules[0].deliver.kind=none"), "CronJob", self.NAME)
        assert none == plain, "deliver.kind=none renders today's CronJob"
        command = plain["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]["command"]
        assert "--deliver" not in command and "--attach" not in command
        pod = self._pod("reporting.schedules[0].deliver.kind=webhook",
                        "reporting.schedules[0].deliver.webhookUrlSecret.name=team-hook",
                        "reporting.schedules[0].deliver.webhookUrlSecret.key=slack",
                        "reporting.schedules[0].deliver.attach=html")
        trigger = pod["containers"][0]
        joined = " ".join(trigger["command"])
        assert "--deliver webhook --webhook-url-file /etc/gsd/deliver/url --attach html" in joined, joined
        assert "team-hook" not in joined and "slack" not in joined, "the Secret is mounted, never an argument"
        mounts = {m["name"]: m for m in trigger["volumeMounts"]}
        assert mounts["deliver-url"] == {"name": "deliver-url", "mountPath": "/etc/gsd/deliver", "readOnly": True}
        assert mounts["trusted-ca-injected"]["readOnly"] is True
        volumes = {v["name"]: v for v in pod["volumes"]}
        assert volumes["deliver-url"]["secret"] == {"secretName": "team-hook", "items": [{"key": "slack", "path": "url"}],
                                                    "defaultMode": 288}
        assert volumes["trusted-ca-injected"]["configMap"] == {"name": "t-group-sync-dashboard-trusted-ca", "optional": True}
        assert _env(trigger, "GSD_TRUSTED_CA_FILE") == "/etc/pki/ca-trust/extracted/pem/injected/ca-bundle.crt"
        cron = _exact(_render(*self.BASE, "reporting.schedules[0].deliver.kind=webhook",
                              "reporting.schedules[0].deliver.webhookUrlSecret.name=team-hook"), "CronJob", self.NAME)
        job = cron["spec"]["jobTemplate"]["spec"]
        assert job["backoffLimit"] == 0 and job["activeDeadlineSeconds"] == 900, "no Kubernetes retry, the same deadline"
        assert "--attach" not in job["template"]["spec"]["containers"][0]["command"]

    def test_t109_11_a_deliver_block_that_cannot_work_is_refused_at_render(self):
        assert "needs deliver.webhookUrlSecret.name" in self._refused("reporting.schedules[0].deliver.kind=webhook")
        assert "is not one of none, webhook" in self._refused("reporting.schedules[0].deliver.kind=smtp")
        assert "is not one of none, html, pdf, csv" in self._refused(
            "reporting.schedules[0].deliver.kind=webhook", "reporting.schedules[0].deliver.webhookUrlSecret.name=h",
            "reporting.schedules[0].deliver.attach=docx")
        assert "needs deliver.kind=webhook" in self._refused("reporting.schedules[0].deliver.attach=html")
        # The scheduled default stores html and json: a pdf to attach must be stored first.
        assert "add pdf to its formats" in self._refused(
            "reporting.schedules[0].deliver.kind=webhook", "reporting.schedules[0].deliver.webhookUrlSecret.name=h",
            "reporting.schedules[0].deliver.attach=pdf")
        self._pod("reporting.schedules[0].deliver.kind=webhook", "reporting.schedules[0].deliver.webhookUrlSecret.name=h",
                  "reporting.schedules[0].deliver.attach=pdf", "reporting.schedules[0].formats[0]=pdf")
```

### Block 10 — `charts/group-sync-dashboard/templates/_helpers.tpl`: `gsd.trustedCaFile`, the one CA list

<!-- block: charts/group-sync-dashboard/templates/_helpers.tpl | edit -->

```text

{{- define "gsd.reportEnabledReports" -}}
```

```text

{{- /* The CA bundles the chart mounts, colon-separated like SSL_CERT_FILE, for GSD_TRUSTED_CA_FILE: read by the
dashboard (gsd/config.py _trusted_ca_context) and by a schedule Job that delivers to a webhook (#109). Empty when
neither trustedCA source is on. */ -}}
{{- define "gsd.trustedCaFile" -}}
{{- $ca := list -}}
{{- if .Values.trustedCA.injected.enabled -}}
{{- $ca = append $ca (printf "%s/injected/ca-bundle.crt" .Values.trustedCA.mountPath) -}}
{{- end -}}
{{- if .Values.trustedCA.existingConfigMap.enabled -}}
{{- $ca = append $ca (printf "%s/enterprise/%s" .Values.trustedCA.mountPath .Values.trustedCA.existingConfigMap.key) -}}
{{- end -}}
{{- join ":" $ca -}}
{{- end -}}

{{- define "gsd.reportEnabledReports" -}}
```

### Block 11 — `charts/group-sync-dashboard/templates/_helpers.tpl`: the deliver block's refusals

<!-- block: charts/group-sync-dashboard/templates/_helpers.tpl | edit -->

```text
{{- fail (printf "reporting.schedules[].name %q must be a short DNS label (it names a CronJob)" (toString $s.name)) -}}
{{- end -}}
```

```text
{{- fail (printf "reporting.schedules[].name %q must be a short DNS label (it names a CronJob)" (toString $s.name)) -}}
{{- end -}}
{{- /* #109: deliver.kind none|webhook; attach only with a webhook, and only a format the schedule stores. */ -}}
{{- $deliver := $s.deliver | default dict -}}
{{- $kind := toString ($deliver.kind | default "none") -}}
{{- $attach := toString ($deliver.attach | default "none") -}}
{{- if not (has $kind (list "none" "webhook")) -}}
{{- fail (printf "reporting.schedules[%s].deliver.kind %q is not one of none, webhook" $s.name $kind) -}}
{{- end -}}
{{- if not (has $attach (list "none" "html" "pdf" "csv")) -}}
{{- fail (printf "reporting.schedules[%s].deliver.attach %q is not one of none, html, pdf, csv" $s.name $attach) -}}
{{- end -}}
{{- if and (eq $kind "none") (ne $attach "none") -}}
{{- fail (printf "reporting.schedules[%s].deliver.attach=%s needs deliver.kind=webhook: there is nothing to attach it to" $s.name $attach) -}}
{{- end -}}
{{- if eq $kind "webhook" -}}
{{- if not (($deliver.webhookUrlSecret | default dict).name) -}}
{{- fail (printf "reporting.schedules[%s].deliver.kind=webhook needs deliver.webhookUrlSecret.name: the Secret whose key holds the URL" $s.name) -}}
{{- end -}}
{{- $stored := $s.formats | default ((($.Values.reporting | default dict).formats | default dict).scheduled) | default list -}}
{{- if and (ne $attach "none") (not (has $attach $stored)) -}}
{{- fail (printf "reporting.schedules[%s].deliver.attach=%s, but the schedule stores %s: add %s to its formats" $s.name $attach (join ", " $stored) $attach) -}}
{{- end -}}
{{- end -}}
```

### Block 12 — `charts/group-sync-dashboard/templates/deployment.yaml`: the dashboard reads the helper (renders unchanged)

<!-- block: charts/group-sync-dashboard/templates/deployment.yaml | edit -->

```yaml
            {{- end }}
            {{- $ca := list }}
            {{- if .Values.trustedCA.injected.enabled }}
            {{- $ca = append $ca (printf "%s/injected/ca-bundle.crt" .Values.trustedCA.mountPath) }}
            {{- end }}
            {{- if .Values.trustedCA.existingConfigMap.enabled }}
            {{- $ca = append $ca (printf "%s/enterprise/%s" .Values.trustedCA.mountPath .Values.trustedCA.existingConfigMap.key) }}
            {{- end }}
            {{- if $ca }}
            # Colon-separated, like SSL_CERT_FILE. Used for any cluster that does not name
            # its own caBundleFile — the normal case for an external, corporate-signed one.
            - name: GSD_TRUSTED_CA_FILE
              value: {{ join ":" $ca | quote }}
            {{- end }}
```

```yaml
            {{- end }}
            {{- with include "gsd.trustedCaFile" . }}
            # Colon-separated, like SSL_CERT_FILE. Used for any cluster that does not name
            # its own caBundleFile — the normal case for an external, corporate-signed one.
            - name: GSD_TRUSTED_CA_FILE
              value: {{ . | quote }}
            {{- end }}
```

### Block 13 — `charts/group-sync-dashboard/templates/report-cronjob.yaml`: the schedule's deliver switch

<!-- block: charts/group-sync-dashboard/templates/report-cronjob.yaml | edit -->

```yaml
{{- range $s := .Values.reporting.schedules }}
---
```

```yaml
{{- range $s := .Values.reporting.schedules }}
{{- $deliver := $s.deliver | default dict }}
{{- $delivers := ne (toString ($deliver.kind | default "none")) "none" }}
{{- $trustedCa := include "gsd.trustedCaFile" $ }}
---
```

### Block 14 — `charts/group-sync-dashboard/templates/report-cronjob.yaml`: the args and the trust env

<!-- block: charts/group-sync-dashboard/templates/report-cronjob.yaml | edit -->

```yaml
                {{- end }}
              env:
                - name: GSD_REPORT_TOKEN_FILE
                  value: /etc/gsd/report/token
              securityContext: {{- toYaml $.Values.securityContext | nindent 16 }}
```

```yaml
                {{- end }}
                {{- if $delivers }}
                # #109: each finished run's facts go to the webhook. The URL is a file from the Secret
                # below, never an argument, so no pod spec, event or `ps` shows it.
                - --deliver
                - {{ $deliver.kind | quote }}
                - --webhook-url-file
                - /etc/gsd/deliver/url
                {{- if ne (toString ($deliver.attach | default "none")) "none" }}
                - --attach
                - {{ $deliver.attach | quote }}
                {{- end }}
                {{- end }}
              env:
                - name: GSD_REPORT_TOKEN_FILE
                  value: /etc/gsd/report/token
                {{- if and $delivers $trustedCa }}
                # The dashboard's trust for an https receiver: the injected and enterprise bundles.
                - name: GSD_TRUSTED_CA_FILE
                  value: {{ $trustedCa | quote }}
                {{- end }}
              securityContext: {{- toYaml $.Values.securityContext | nindent 16 }}
```

### Block 15 — `charts/group-sync-dashboard/templates/report-cronjob.yaml`: the mounts

<!-- block: charts/group-sync-dashboard/templates/report-cronjob.yaml | edit -->

```yaml
                  readOnly: true
                {{- end }}
```

```yaml
                  readOnly: true
                {{- end }}
                {{- if $delivers }}
                - name: deliver-url
                  mountPath: /etc/gsd/deliver
                  readOnly: true
                {{- if $.Values.trustedCA.injected.enabled }}
                - name: trusted-ca-injected
                  mountPath: {{ $.Values.trustedCA.mountPath }}/injected
                  readOnly: true
                {{- end }}
                {{- if $.Values.trustedCA.existingConfigMap.enabled }}
                - name: trusted-ca-enterprise
                  mountPath: {{ $.Values.trustedCA.mountPath }}/enterprise
                  readOnly: true
                {{- end }}
                {{- end }}
```

### Block 16 — `charts/group-sync-dashboard/templates/report-cronjob.yaml`: the Secret and trust volumes

<!-- block: charts/group-sync-dashboard/templates/report-cronjob.yaml | edit -->

```yaml
            {{- end }}
{{- end }}
```

```yaml
            {{- end }}
            {{- if $delivers }}
            # One key of the operator's Secret, as the file `url`; 0440 like the report token.
            - name: deliver-url
              secret:
                secretName: {{ $deliver.webhookUrlSecret.name | quote }}
                items:
                  - key: {{ $deliver.webhookUrlSecret.key | default "url" | quote }}
                    path: url
                defaultMode: 288
            {{- if $.Values.trustedCA.injected.enabled }}
            - name: trusted-ca-injected
              configMap:
                name: {{ include "gsd.fullname" $ }}-trusted-ca
                # optional, as on the dashboard: OpenShift fills it shortly after creation.
                optional: true
            {{- end }}
            {{- if $.Values.trustedCA.existingConfigMap.enabled }}
            - name: trusted-ca-enterprise
              configMap:
                name: {{ $.Values.trustedCA.existingConfigMap.name }}
            {{- end }}
            {{- end }}
{{- end }}
```

### Block 17 — `charts/group-sync-dashboard/values.yaml`: the schedules comment: nothing is mailed, reworded

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->

```yaml
  # Unattended runs. Each entry is a CronJob on the report image that POSTs one run with the
  # service token and waits for it (exit status = run status). Nothing is mailed; the artefact
  # lands in the artefact store like any other. `report` must be an enabled catalogue name.
  # A schedule is CLUSTER-AGNOSTIC (#149 R1): the service resolves every enabled cluster from its
```

```yaml
  # Unattended runs. Each entry is a CronJob on the report image that POSTs one run with the
  # service token and waits for it (exit status = run status). The artefact lands in the artefact
  # store like any other; nothing is mailed. `report` must be an enabled catalogue name.
  # A schedule is CLUSTER-AGNOSTIC (#149 R1): the service resolves every enabled cluster from its
```

### Block 18 — `charts/group-sync-dashboard/values.yaml`: the `deliver` comment and example

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->

```yaml
  #     enabled: false
  schedules: []
```

```yaml
  #     enabled: false
  #
  # `deliver` (#109, docs/specs/SPEC_F4_webhook_delivery.md): kind none (the default, today's CronJob) or
  # webhook. With webhook, each finished run of the fan-out is POSTed as one CloudEvent (the run's facts:
  # report, cluster, run id, status, schedule, sha256, finished_at, sizes) to the URL held in a Secret you
  # create (`oc create secret generic team-hook --from-literal=url=https://...`), mounted read-only into the
  # Job and never printed. attach: none|html|pdf|csv adds that artefact, base64, up to 5 MiB; it must be a
  # format the schedule stores. Retried 4 times with backoff for 408, 429, 5xx and network errors; a run
  # not delivered fails the Job like a failed run. The Job's egress to the receiver: chart README.
  #   - name: weekly-groups
  #     schedule: "0 23 * * 0"
  #     report: groups
  #     deliver:
  #       kind: webhook
  #       webhookUrlSecret: {name: team-hook, key: url}
  #       attach: html
  schedules: []
```

### Block 19 — `charts/group-sync-dashboard/README.md`: the `deliver` row and the Job's egress

<!-- block: charts/group-sync-dashboard/README.md | edit -->

```markdown
| `reporting.schedules` | `[]` | unattended runs: one CronJob per entry (`name`, `schedule`, `report`, optional `params`, `enabled`, `cluster`, `formats`) posting with the service token; nothing is mailed. **Cluster-agnostic**: the service resolves every enabled cluster from its snapshot and runs one per cluster, each tagged `schedule:<name>`; `cluster` pins one. `enabled: false` keeps the CronJob and **suspends** it (`spec.suspend`) — definition, history and audit stay; remove the entry to retire it | `report` must be an enabled catalogue name; `name` a DNS label |
| `reporting.podDisruptionBudget.enabled` / `.maxUnavailable` / `.minAvailable` | `true` / `1` / `""` | the report Deployment's own budget; same semantics as the dashboard's | selects the report pods only, never the schedule Jobs |
| `reporting.resources` / `.nodeSelector` / `.tolerations` / `.affinity` | requests `50m`/`128Mi`, limits `500m`/`768Mi` / `{}` / `[]` / `{}` | the report pod's own scheduling; nothing is derived from the data claim's access mode | — |

```

```markdown
| `reporting.schedules` | `[]` | unattended runs: one CronJob per entry (`name`, `schedule`, `report`, optional `params`, `enabled`, `cluster`, `formats`) posting with the service token; nothing is mailed. **Cluster-agnostic**: the service resolves every enabled cluster from its snapshot and runs one per cluster, each tagged `schedule:<name>`; `cluster` pins one. `enabled: false` keeps the CronJob and **suspends** it (`spec.suspend`) — definition, history and audit stay; remove the entry to retire it | `report` must be an enabled catalogue name; `name` a DNS label |
| `reporting.schedules[].deliver` | absent (`kind: none`) | **#109.** `kind: webhook` POSTs each finished run of the fan-out, as one CloudEvents 1.0 event (`application/cloudevents+json`; `id` is the run id, `data` the run's report, cluster, status, schedule, sha256, `finished_at`, sizes and error), to the URL in `webhookUrlSecret` (`name`, `key` default `url`), mounted read-only in the Job and never printed. `attach: html\|pdf\|csv` adds that artefact base64 up to 5 MiB, else names why it is omitted. 408, 429, 5xx and network errors are retried (4 attempts, full-jitter backoff, `Retry-After` honoured, inside the Job's deadline); a run not delivered fails the Job. The receiver must take generic JSON: a Slack incoming webhook or a Teams Workflows trigger needs its own adapter | `kind` none or webhook; webhook needs `webhookUrlSecret.name`; `attach` only with webhook, and only a format the schedule stores |
| `reporting.podDisruptionBudget.enabled` / `.maxUnavailable` / `.minAvailable` | `true` / `1` / `""` | the report Deployment's own budget; same semantics as the dashboard's | selects the report pods only, never the schedule Jobs |
| `reporting.resources` / `.nodeSelector` / `.tolerations` / `.affinity` | requests `50m`/`128Mi`, limits `500m`/`768Mi` / `{}` / `[]` / `{}` | the report pod's own scheduling; nothing is derived from the data claim's access mode | — |

**Egress of the schedule Job (#109).** The chart renders no egress policy: the report pod's NetworkPolicy
is `policyTypes: [Ingress]` and selects the report pod only, and nothing selects the schedule Job's pods
(`app.kubernetes.io/component: report-schedule`). A delivering Job reaches DNS, the report Service on 8443 and
the receiver. In a namespace whose own policy denies egress by default, allow those three for the Job's
pods yourself: a NetworkPolicy matches CIDRs and ports, never a hostname, and the receiver's host sits in a
Secret the chart cannot read; on OVN-Kubernetes an `EgressFirewall` can allow it by `dnsName`. An https
receiver is verified with the dashboard's trust (`trustedCA.injected`, `trustedCA.existingConfigMap`); a
receiver behind an HTTP proxy is not supported by the chart's values (the Job sets no proxy variables).

```

### Block 20 — `environments/crc.yaml`: the lab's suspended delivery-walk schedule

<!-- block: environments/crc.yaml | edit -->

```yaml
      enabled: false

```

```yaml
      enabled: false
    # #109: the delivery walk's schedule. Suspended, so it fires only when the walk runs
    # `oc create job --from=cronjob/...` inside the window; its Secret and receiver exist only during the walk
    # (docs/specs/SPEC_F4_webhook_delivery.md §5), so a fire outside the walk could not start its pod.
    - name: delivery-walk
      schedule: "0 23 * * 0"
      report: groups
      enabled: false
      deliver:
        kind: webhook
        webhookUrlSecret: {name: gsd-delivery-walk, key: url}
        attach: html

```

### Block 21 — `docs/CHANGELOG.md`: the Unreleased entry

<!-- block: docs/CHANGELOG.md | edit -->

```markdown
## Unreleased

```

```markdown
## Unreleased

- **Webhook delivery of scheduled reports (#109, Epic F #386, `docs/specs/SPEC_F4_webhook_delivery.md`;
  application 4.4.0, chart 0.67.0).** A schedule with `deliver: {kind: webhook, webhookUrlSecret: {name, key}}`
  POSTs each finished run of its fan-out as one CloudEvents 1.0 event (the run's facts; `id` is the run id) to the
  URL in that Secret, mounted read-only into the Job; `attach: html|pdf|csv` adds the artefact base64 up to 5 MiB.
  408, 429, 5xx and network errors are retried four times with full-jitter backoff and `Retry-After`; a run not
  delivered fails the Job. The URL is never printed: a failure names the HTTP status or the exception's class.
  A schedule without `deliver` renders the same CronJob; the report service still makes no outbound call; a
  window skip (409) delivers nothing; no RBAC change.

```

### Block 22 — `local-development/pyproject.toml`: application 4.4.0

<!-- block: local-development/pyproject.toml | edit -->

```toml
# are unaffected, byte-for-byte.
version = "4.3.0"
description = "Read-only multi-cluster dashboard for the redhat-cop group-sync-operator"
```

```toml
# are unaffected, byte-for-byte.
version = "4.4.0"
description = "Read-only multi-cluster dashboard for the redhat-cop group-sync-operator"
```

### Block 23 — `local-development/gsd/__init__.py`: application 4.4.0

<!-- block: local-development/gsd/__init__.py | edit -->

```python
# before that test existed nothing did.
__version__ = "4.3.0"

```

```python
# before that test existed nothing did.
__version__ = "4.4.0"

```

### Block 24 — `charts/group-sync-dashboard/Chart.yaml`: chart 0.67.0 and its history line

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->

```yaml
# README's reports paragraph names report-diff; no key, default, template or RBAC change.
version: 0.66.7
# 0.8.0 (2026-09-03). A Users tab — every user with a synced membership, filtered as you type on
```

```yaml
# README's reports paragraph names report-diff; no key, default, template or RBAC change.
# CHART 0.67.0 (2026-10-04), MINOR: `reporting.schedules[].deliver` {kind, webhookUrlSecret {name, key}, attach}
# renders the trigger's delivery args, the URL Secret and the trust bundles into a schedule's CronJob, refused at
# render when it cannot work; a schedule without it renders as before; `gsd.trustedCaFile` is the one CA list for
# the dashboard and the Job; appVersion moves to application 4.4.0 (below); #109, SPEC_F4. No RBAC change.
version: 0.67.0
# 0.8.0 (2026-09-03). A Users tab — every user with a synced membership, filtered as you type on
```

### Block 25 — `charts/group-sync-dashboard/Chart.yaml`: application 4.4.0's history line

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->

```yaml
# 4.3.0 (2026-10-03). What changed between two runs: a report-diff run compares the sealed data of two finished runs of one report on one cluster, rows removed and added per table, stored as a sealed manual run naming both inputs and their sha256s (#108). MINOR.
appVersion: "4.3.0"

```

```yaml
# 4.3.0 (2026-10-03). What changed between two runs: a report-diff run compares the sealed data of two finished runs of one report on one cluster, rows removed and added per table, stored as a sealed manual run naming both inputs and their sha256s (#108). MINOR.
# 4.4.0 (2026-10-04). Webhook delivery of scheduled reports: each finished run of a schedule's fan-out is POSTed as one CloudEvent to the URL in a mounted Secret, retried for 408, 429, 5xx and network errors, never printing the URL; a run not delivered fails the Job (#109). MINOR.
appVersion: "4.4.0"

```

### Block 26 — `docs/DESIGN_reporting_output_and_delivery.md`: the status line points here

<!-- block: docs/DESIGN_reporting_output_and_delivery.md | edit -->

```markdown
(#108), which compares stable coverage conclusions and the sealed sections, and keys blocks by section, kind, title and columns (SPEC_F3
§2.4).** Record: `docs/REVIEW_reporting_output_delivery.md`. Four
features from `docs/REPORTING_ENHANCEMENTS.md`, taken forward
```

```markdown
(#108), which compares stable coverage conclusions and the sealed sections, and keys blocks by section, kind, title and columns (SPEC_F3
§2.4). §4 (delivery) is built by `docs/specs/SPEC_F4_webhook_delivery.md` (#109), which delivers per run as a
CloudEvent, retries inside the Job's deadline and reuses the dashboard's CA trust (SPEC_F4 §2.4).** Record: `docs/REVIEW_reporting_output_delivery.md`. Four
features from `docs/REPORTING_ENHANCEMENTS.md`, taken forward
```

### Block 27 — `docs/DESIGN_reporting_service.md`: §5.6 names delivery

<!-- block: docs/DESIGN_reporting_service.md | edit -->

```markdown

A `reporting.schedules[]` entry renders a CronJob on the **report image** whose one container runs `python3.14 -m gsd.reporting.trigger --report <name> --schedule <name> [--cluster <id>] [--param k=v]… --wait` (no `--cluster` since #149 R1: the service fans the run out to every enabled cluster in its snapshot; `--format` only when the schedule sets one, R3), posting to the report Service with the service token over TLS (CA from the same ConfigMap mount). It writes nothing but the artefact; nothing is mailed (the parked design's question A: "somewhere to put the file and someone to send it to" — the artefact store is the "somewhere"; sending is out of scope and recorded in operator question 4). The Job pod carries `app.kubernetes.io/component: report-schedule` (never `gsd.selectorLabels` — the B1 lesson at `docs/specs/SPEC_B1_offsite_backup.md#Pod labels`).

```

```markdown

A `reporting.schedules[]` entry renders a CronJob on the **report image** whose one container runs `python3.14 -m gsd.reporting.trigger --report <name> --schedule <name> [--cluster <id>] [--param k=v]… --wait` (no `--cluster` since #149 R1: the service fans the run out to every enabled cluster in its snapshot; `--format` only when the schedule sets one, R3), posting to the report Service with the service token over TLS (CA from the same ConfigMap mount). It writes nothing but the artefact; nothing is mailed (the parked design's question A: "somewhere to put the file and someone to send it to" — the artefact store is the "somewhere"; sending is out of scope and recorded in operator question 4). Since #109 a schedule may also deliver each finished run to a webhook from the Job, never from the service (`docs/specs/SPEC_F4_webhook_delivery.md`). The Job pod carries `app.kubernetes.io/component: report-schedule` (never `gsd.selectorLabels` — the B1 lesson at `docs/specs/SPEC_B1_offsite_backup.md#Pod labels`).

```
