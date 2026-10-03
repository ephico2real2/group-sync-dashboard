"""Runs INSIDE the report pod (#270 lab check). Reads the viewer and the dashboard-minted ticket from stdin, so
neither is on a command line; queues two viewer runs of one report over the snapshot the service reads now, waits
for both, and prints one JSON document: the snapshot before and after, each run record and each run's .json."""
import json, ssl, sys, time, urllib.request

viewer, ticket, cluster, report = (sys.stdin.readline().strip() for _ in range(4))
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE  # loopback only
H = {"X-Forwarded-User": viewer, "X-GSD-Report-Ticket": ticket, "Content-Type": "application/json"}

def call(method, path, body=None):
    req = urllib.request.Request("https://127.0.0.1:8443" + path, method=method, headers=H,
                                 data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(req, context=ctx, timeout=60) as r:
        return r.read()

def wait(run_id):
    for _ in range(120):
        run = json.loads(call("GET", f"/report/api/runs/{run_id}"))
        if run["status"] in ("done", "failed"):
            return run
        time.sleep(2)
    raise SystemExit(f"run {run_id} did not finish in 240 s")

out = {"snapshot_before": json.loads(call("GET", "/report/api/snapshot")), "runs": []}
for _ in range(2):
    queued = json.loads(call("POST", "/report/api/runs", {"report": report, "cluster": cluster, "params": {},
                                                          "formats": ["html", "pdf"]}))
    run = wait(queued["id"])
    doc = json.loads(call("GET", f"/report/api/runs/{run['id']}/artifact?format=json")) if run["status"] == "done" else None
    out["runs"].append({"record": run, "json": doc})
out["snapshot_after"] = json.loads(call("GET", "/report/api/snapshot"))
print(json.dumps(out))
