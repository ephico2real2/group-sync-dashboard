"""The schedule Job's one command: POST a run with the service token, optionally wait for it.

    python3.14 -m gsd.reporting.trigger --url https://<svc>:8443 --report compliance-snapshot \
        --schedule weekly --wait [--cluster crc-local] [--param window_days=30]... [--format html]

A schedule is cluster-agnostic (R1): with no --cluster the service fans the run out to every enabled
cluster in its snapshot and answers with all of them; --cluster pins one. Formats default by origin
in the service (R3: a schedule stores html+json); --format overrides for this schedule only.

Exit 0 when the run finished `done`, 1 on any refusal or a `failed` run — so the Job's status is
the run's status and kube_job_status_failed can alert on it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import httpx


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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="gsd.reporting.trigger")
    ap.add_argument("--url", required=True, help="the report Service, e.g. https://gsd-report.ns.svc:8443")
    ap.add_argument("--report", required=True)
    ap.add_argument("--cluster", default="", help="pin one cluster; omitted = every enabled cluster in the snapshot")
    ap.add_argument("--param", action="append", default=[], help="k=v, repeatable — scalar params only")
    ap.add_argument("--params-json", default="",
                    help="the params as a JSON object; required for structured params like `selectors` "
                         "that a k=v string cannot express (the chart renders schedules[].params this way)")
    ap.add_argument("--format", action="append", default=[], choices=["html", "pdf"])
    ap.add_argument("--schedule", required=True, help="the schedule's name, recorded as generated_by=schedule:<name>")
    ap.add_argument("--token-file", default=os.environ.get("GSD_REPORT_TOKEN_FILE", "/etc/gsd/report/token"))
    ap.add_argument("--ca-file", default=os.environ.get("GSD_REPORT_CA_FILE", ""), help="PEM bundle for the Service certificate; empty = system trust")
    ap.add_argument("--wait", action="store_true", help="poll until the run finishes; exit 1 if it failed")
    ap.add_argument("--timeout", type=int, default=600)
    a = ap.parse_args(argv)
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

    with httpx.Client(base_url=a.url, headers=headers, verify=verify, timeout=30.0) as c:
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
        failed = 0
        while pending and time.monotonic() < deadline:
            time.sleep(2)
            for run_id in list(pending):
                run = c.get(f"/report/api/runs/{run_id}").json()
                if run["status"] in ("done", "failed"):
                    print(json.dumps({"id": run["id"], "cluster": run.get("cluster"), "status": run["status"],
                                      "sha256": run.get("sha256"), "bytes": run.get("bytes"), "error": run.get("error")}))
                    failed += run["status"] == "failed"
                    del pending[run_id]
        if pending:
            print(f"timed out waiting for {len(pending)} run(s): {', '.join(sorted(pending))}", file=sys.stderr)
            return 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
