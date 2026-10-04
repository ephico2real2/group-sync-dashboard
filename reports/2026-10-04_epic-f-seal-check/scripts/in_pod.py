"""Runs INSIDE the report pod: Epic F's seal check, as its Definition of Done words it (#386). Reads the viewer, a
dashboard-minted ticket and an earlier run id from stdin, so none is on a command line; prints JSON lines.

  1. Two `compliance-snapshot` runs for `dashboard`, requested one after the other: the sha256 that
     GET /report/api/runs/{id} returns for each, and the snapshot each was built from.
  2. The earlier run (an older snapshot) read the same way, and a `report-diff` from it to the first new run: its
     totals say whether the data changed between the two snapshots."""
import json, pathlib, ssl, sys, time, urllib.error, urllib.request

viewer, ticket, earlier = (sys.stdin.readline().strip() for _ in range(3))
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE  # loopback only
H = {"X-Forwarded-User": viewer, "X-GSD-Report-Ticket": ticket, "Content-Type": "application/json"}


def call(method, path, body=None):
    req = urllib.request.Request("https://127.0.0.1:8443" + path, method=method, headers=H,
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def finished(body):
    status, run = call("POST", "/report/api/runs", body)
    assert status == 202, (status, run)
    for _ in range(150):
        status, run = call("GET", f"/report/api/runs/{run['id']}")
        if run.get("status") in ("done", "failed"):
            return run
        time.sleep(2)
    return run


def facts(run):
    return {k: run.get(k) for k in ("id", "status", "sha256", "snapshot_stamp", "generated_by")}


first = finished({"report": "compliance-snapshot", "cluster": "dashboard", "params": {}, "formats": ["html"]})
second = finished({"report": "compliance-snapshot", "cluster": "dashboard", "params": {}, "formats": ["html"]})
_, a = call("GET", f"/report/api/runs/{first['id']}")
_, b = call("GET", f"/report/api/runs/{second['id']}")
print(json.dumps({"check": "two runs, one after the other", "first": facts(a), "second": facts(b),
                  "same_sha256": a.get("sha256") == b.get("sha256"),
                  "same_snapshot": a.get("snapshot_stamp") == b.get("snapshot_stamp")}))

_, old = call("GET", f"/report/api/runs/{earlier}")
diff = finished({"report": "report-diff", "cluster": "dashboard", "params": {"base": earlier, "head": first["id"]},
                 "formats": ["html"]})
totals = json.loads(pathlib.Path("/artifacts", diff["id"], "report.json").read_text()).get("totals") \
    if diff.get("status") == "done" else None
print(json.dumps({"check": "an earlier run over an older snapshot", "earlier": facts(old), "new": facts(a),
                  "different_snapshot": old.get("snapshot_stamp") != a.get("snapshot_stamp"),
                  "different_sha256": old.get("sha256") != a.get("sha256"),
                  "diff": {"id": diff.get("id"), "status": diff.get("status"), "totals": totals}}))
