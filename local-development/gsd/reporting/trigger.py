"""The schedule Job's one command: POST a run with the service token, optionally wait for it.

    python3.14 -m gsd.reporting.trigger --url https://<svc>:8443 --report compliance-snapshot \
        --schedule weekly --wait [--cluster crc-local] [--param window_days=30]... [--format html]

A schedule is cluster-agnostic (R1): with no --cluster the service fans the run out to every enabled
cluster in its snapshot and answers with all of them; --cluster pins one. Formats default by origin
in the service (R3: a schedule stores html+json); --format overrides for this schedule only.

Exit 0 when the run finished `done`, 1 on any refusal or a `failed` run — so the Job's status is
the run's status and kube_job_status_failed can alert on it.

With --deliver webhook (#109, docs/specs/SPEC_F4_webhook_delivery.md) each finished run's facts are POSTed,
as one CloudEvent, to the URL in --webhook-url-file (a mounted Secret). The URL is never printed: a failed
delivery names the HTTP status or the exception's class, and an undelivered run exits 1 like a failed one.
"""

from __future__ import annotations

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


#: Only a POST that never REACHED the service is repeated, and only here, in-process: the Job's own
#: Kubernetes retry is off (backoffLimit 0) because a retry pod would POST the whole fan-out again
#: after a 202 and render every cluster twice (review of PR #220, OB3). A read timeout is not repeated —
#: the request may have queued.
POST_ATTEMPTS, POST_RETRY_SECONDS = 3, 10


def _post(c: httpx.Client, body: dict) -> httpx.Response:
    attempt = 0
    while True:
        attempt += 1
        try:
            return c.post("/report/api/runs", json=body)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            if attempt >= POST_ATTEMPTS:
                raise
            print(f"POST did not reach the service ({type(exc).__name__}: {exc}); "
                  f"retrying in {POST_RETRY_SECONDS}s ({attempt}/{POST_ATTEMPTS})", file=sys.stderr)
            time.sleep(POST_RETRY_SECONDS)


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
    except (OSError, ValueError) as exc:     # ValueError: UnicodeDecodeError, a file that is not UTF-8
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
    if raw.isascii() and raw.isdigit():
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
    try:
        r = service.get(f"/report/api/runs/{run['id']}/artifact", params={"format": fmt})
    except httpx.HTTPError as exc:
        return {"format": fmt, "omitted": f"the artefact read failed ({type(exc).__name__})"}
    if r.status_code != 200:
        return {"format": fmt, "omitted": f"the artefact read answered {r.status_code}"}
    actual_size = len(r.content)
    if actual_size > ATTACH_MAX_BYTES:
        return {"format": fmt, "omitted": f"{actual_size} bytes read is over the {ATTACH_MAX_BYTES}-byte cap"}
    return {"format": fmt, "media_type": r.headers.get("content-type"), "bytes": actual_size,
            "content_base64": base64.b64encode(r.content).decode("ascii")}


def _event(run: dict, schedule: str, source: str, attachment: dict | None) -> dict:
    """One finished run as a CloudEvents 1.0 structured-mode event: the run's facts in `data`."""
    data = {"report": run.get("report"), "cluster": run.get("cluster"), "run_id": run["id"],
            "status": run["status"], "schedule": schedule, "sha256": run.get("sha256"),
            "finished_at": run.get("finished_at"), "bytes": run.get("bytes") or {}, "error": run.get("error")}
    if attachment is not None:
        data["attachment"] = attachment
    event = {"specversion": "1.0", "id": run["id"], "source": source, "type": EVENT_TYPE,
             "datacontenttype": "application/json", "data": data}
    if run.get("finished_at"):          # CloudEvents `time` is optional: absent, never null
        event["time"] = run["finished_at"]
    return event


def _deliver(hook: httpx.Client, url: str, event: dict, deadline: float) -> bool:
    """POST the event, retrying what may succeed later with full-jitter backoff (or the receiver's
    Retry-After) while the Job's deadline allows. Prints the status or the exception's CLASS, never str():
    httpx's HTTPStatusError and a TLS ConnectError quote the URL or its host (SPEC_F4 §2.3)."""
    run_id = event["id"]
    body = json.dumps(event).encode("utf-8")
    headers = {"Content-Type": "application/cloudevents+json; charset=utf-8"}
    for attempt in range(1, DELIVER_ATTEMPTS + 1):
        # §3.3: an attempt starts only if it can finish before the wait's deadline, the first one included and
        # after a sleep that overran (review of #109: OB3 F3, Codex F1).
        if time.monotonic() + DELIVER_TIMEOUT_SECONDS > deadline:
            print(f"delivery failed for run {run_id}: no attempt fits before the wait's deadline "
                  f"(after {attempt - 1} attempt(s))", file=sys.stderr)
            return False
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
    ap = argparse.ArgumentParser(prog="gsd.reporting.trigger")
    ap.add_argument("--url", required=True, help="the report Service, e.g. https://gsd-report.ns.svc:8443")
    ap.add_argument("--report", required=True)
    ap.add_argument("--cluster", default="", help="pin one cluster; omitted = every enabled cluster in the snapshot")
    ap.add_argument("--param", action="append", default=[], help="k=v, repeatable — scalar params only")
    ap.add_argument("--params-json", default="",
                    help="the params as a JSON object; required for structured params like `selectors` "
                         "that a k=v string cannot express (the chart renders schedules[].params this way)")
    ap.add_argument("--format", action="append", default=[], choices=["html", "csv"])
    ap.add_argument("--schedule", required=True, help="the schedule's name, recorded as generated_by=schedule:<name>")
    ap.add_argument("--token-file", default=os.environ.get("GSD_REPORT_TOKEN_FILE", "/etc/gsd/report/token"))
    ap.add_argument("--ca-file", default=os.environ.get("GSD_REPORT_CA_FILE", ""), help="PEM bundle for the Service certificate; empty = system trust")
    ap.add_argument("--wait", action="store_true", help="poll until the run finishes; exit 1 if it failed")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--deliver", default="none", choices=["none", "webhook"],
                    help="send each finished run's facts to a webhook (needs --wait and --webhook-url-file)")
    ap.add_argument("--webhook-url-file", default="", help="a file holding the webhook URL (a mounted Secret)")
    ap.add_argument("--attach", default="none", choices=["none", "html", "csv"],
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
    if a.params_json:
        try:
            parsed = json.loads(a.params_json)
        except ValueError as exc:
            print(f"--params-json is not valid JSON: {exc}", file=sys.stderr)
            return 1
        if not isinstance(parsed, dict):
            print("--params-json must be a JSON object", file=sys.stderr)
            return 1
        params.update(parsed)
    for kv in a.param:                    # scalar overrides, back-compat
        k, _, v = kv.partition("=")
        params[k] = v
    with open(a.token_file, "rb") as fh:
        token = fh.read().strip().decode("utf-8")
    headers = {"Authorization": f"Bearer {token}"}
    verify = a.ca_file or True
    body = {"report": a.report, "params": params, "schedule": a.schedule}
    if a.cluster:
        body["cluster"] = a.cluster
    if a.format:
        body["formats"] = a.format

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
        if r.status_code == 409:
            # The reporting window is closed (design §5): a schedule firing outside its window is a SKIP,
            # not a failure. Exit 0 so the CronJob is not marked failed and does not retry into the
            # window; the run simply did not happen. Any other non-202 (a real refusal) stays exit 1.
            print(json.dumps({"skipped": "outside the reporting window",
                              "retry_after_seconds": r.headers.get("Retry-After")}))
            return 0
        if r.status_code != 202:
            print(f"refused: {r.status_code} {r.text}", file=sys.stderr)
            return 1
        answer = r.json()
        fanned = "runs" in answer
        pending = {x["id"]: x for x in (answer["runs"] if fanned else [answer])}
        if not pending:
            # A fan-out that reached no cluster is not a run that happened: the Job fails and says so.
            print("the service queued no run (no enabled cluster in its snapshot?)", file=sys.stderr)
            return 1
        if fanned:
            print(json.dumps({"submitted": sorted(pending), "report": a.report,
                              "clusters": sorted(x.get("cluster", "") for x in pending.values())}))
        else:
            print(json.dumps({"submitted": next(iter(pending)), "report": a.report}))   # the single-run line, unchanged
        if not a.wait:
            return 0
        # Every run of the fan-out is waited for; the Job fails if ANY failed, and says which.
        deadline = time.monotonic() + a.timeout
        failed = undelivered = 0
        while pending and time.monotonic() < deadline:
            time.sleep(2)
            for run_id in list(pending):
                run = c.get(f"/report/api/runs/{run_id}").json()
                if run["status"] in ("done", "failed"):
                    print(json.dumps({"id": run["id"], "cluster": run.get("cluster"), "status": run["status"],
                                      "sha256": run.get("sha256"), "bytes": run.get("bytes"), "error": run.get("error")}))
                    failed += run["status"] == "failed"
                    del pending[run_id]
                    if hook is not None:
                        attached = _attachment(c, run, a.attach) if a.attach != "none" and run["status"] == "done" else None
                        undelivered += not _deliver(hook, hook_url, _event(run, a.schedule, a.url, attached), deadline)
        if pending:
            print(f"timed out waiting for {len(pending)} run(s): {', '.join(sorted(pending))}", file=sys.stderr)
            return 1
    return 1 if failed or undelivered else 0


if __name__ == "__main__":
    sys.exit(main())
