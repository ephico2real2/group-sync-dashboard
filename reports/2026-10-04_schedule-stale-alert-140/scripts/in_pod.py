"""Runs INSIDE the report pod (#140 lab check): the schedule-status series from /report/metrics and each schedule's
state from /report/api/status, read on the loopback with the service token (read from its file, never printed)."""
import json, ssl, urllib.request
token = open("/etc/gsd/report/token").read().strip()
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE  # loopback only
def get(path, auth):
    h = {"Authorization": f"Bearer {token}"} if auth else {}
    return urllib.request.urlopen(urllib.request.Request("https://127.0.0.1:8443" + path, headers=h), context=ctx, timeout=30).read().decode()
series = [l for l in get("/report/metrics", False).splitlines() if l.startswith("gsd_report_schedule_status{")]
status = json.loads(get("/report/api/status", True))
print(json.dumps({"series": series, "page": [{"name": s["name"], "status": s["status"]} for s in status.get("schedules", [])]}))
