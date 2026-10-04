"""Runs INSIDE the report pod (#108 lab walk). Reads the viewer, the dashboard-minted ticket, the cluster, the report
and its parameters (JSON) from stdin, so none is on a command line; queues one viewer run, waits for it, and prints
its run record as JSON."""
import json, ssl, sys, time, urllib.request

viewer, ticket, cluster, report, params = (sys.stdin.readline().strip() for _ in range(5))
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE  # loopback only
H = {"X-Forwarded-User": viewer, "X-GSD-Report-Ticket": ticket, "Content-Type": "application/json"}

def call(method, path, body=None):
    req = urllib.request.Request("https://127.0.0.1:8443" + path, method=method, headers=H,
                                 data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(req, context=ctx, timeout=60) as r:
        return json.loads(r.read())

queued = call("POST", "/report/api/runs", {"report": report, "cluster": cluster, "params": json.loads(params),
                                           "formats": ["html"]})
for _ in range(120):
    run = call("GET", f"/report/api/runs/{queued['id']}")
    if run["status"] in ("done", "failed"):
        break
    time.sleep(2)
print(json.dumps(run))
