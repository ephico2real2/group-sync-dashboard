"""Runs INSIDE the report pod: for each run id on stdin, the sha256 and size of its html artefact, read through the
service's own API with the service token on the loopback (the token is read from its file and never printed)."""
import hashlib, json, ssl, sys, urllib.request
token = open("/etc/gsd/report/token").read().strip()
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE  # loopback only
for run_id in sys.stdin.read().split():
    req = urllib.request.Request(f"https://127.0.0.1:8443/report/api/runs/{run_id}/artifact?format=html",
                                 headers={"Authorization": f"Bearer {token}"})
    body = urllib.request.urlopen(req, context=ctx, timeout=60).read()
    print(json.dumps({"id": run_id, "html_sha256": hashlib.sha256(body).hexdigest(), "html_bytes": len(body)}))
