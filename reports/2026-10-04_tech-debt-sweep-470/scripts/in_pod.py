"""Runs INSIDE the report pod (the Tech debt sweep's lab checks). Reads the viewer and a dashboard-minted ticket from
stdin, so neither is on a command line, and prints one JSON line per check. Nothing secret is printed.

  #585  the deployed cron parser: named months and weekdays read like their numbers; a stepped weekday ends at SAT;
        an unknown name is refused.
  #588  a diff whose base is newer than its head is refused with 422 and its sentence, and adds no run.
  #589  one access-certification run, through the service: its sealed Campaign section has no "Data as of" row,
        and page one (not sealed) still has it."""
import json, pathlib, ssl, sys, time, urllib.error, urllib.request

from gsd.reporting import cron

viewer, ticket = (sys.stdin.readline().strip() for _ in range(2))
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE  # loopback only
H = {"X-Forwarded-User": viewer, "X-GSD-Report-Ticket": ticket, "Content-Type": "application/json"}
ART = pathlib.Path("/artifacts")


def show(check, **facts):
    print(json.dumps({"check": check, **facts}), flush=True)


def call(method, path, body=None):
    """(status, body) of one loopback call; an HTTP error answer is a result, not an exception."""
    req = urllib.request.Request("https://127.0.0.1:8443" + path, method=method, headers=H,
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def records():
    return [json.loads(p.read_text()) for p in ART.glob("*/run.json")]


# #585
pairs = [("0 22 * * MON-FRI", "0 22 * * 1-5"), ("0 5 1 jan,Jul *", "0 5 1 1,7 *"), ("0 22 * * sun", "0 22 * * 0")]
show("585 names read like numbers", cron=cron.__file__,
     pairs=[{"named": a, "numeric": b, "equal": cron.parse(a).weekdays == cron.parse(b).weekdays
             and cron.parse(a).months == cron.parse(b).months} for a, b in pairs])
show("585 a stepped weekday ends at SAT", weekdays={e: sorted(cron.parse(e).weekdays) for e in ("0 22 * * MON/2", "0 22 * * 1/2")})
try:
    cron.parse("0 22 * * FUNDAY")
    show("585 an unknown name is refused", refused=False)
except cron.CronError as exc:
    show("585 an unknown name is refused", refused=True, error=str(exc))

# #588: the two newest finished `groups` runs on `dashboard` that still have their .json, sent newest-first
done = sorted(r["id"] for r in records() if r.get("status") == "done" and r.get("report") == "groups"
              and r.get("cluster") == "dashboard" and (ART / r["id"] / "report.json").is_file())
older, newer = done[-2], done[-1]
before = len(records())
status, body = call("POST", "/report/api/runs", {"report": "report-diff", "cluster": "dashboard",
                                                 "params": {"base": newer, "head": older}, "formats": ["html"]})
show("588 a reversed diff is refused", base=newer, head=older, status=status, detail=body.get("detail"),
     runs_before=before, runs_after=len(records()))

# #589
status, queued = call("POST", "/report/api/runs", {
    "report": "access-certification", "cluster": "dashboard", "formats": ["html"],
    "params": {"campaign": "Tech debt sweep lab check (#589)", "due": "2026-10-31", "reviewer": viewer}})
run = queued
for _ in range(120):
    if status != 202 or run.get("status") in ("done", "failed"):
        break
    time.sleep(2)
    status_get, run = call("GET", f"/report/api/runs/{queued['id']}")
doc = json.loads((ART / run["id"] / "report.json").read_text()) if run.get("status") == "done" else {}


def pairs_of(section):
    """Every key/value pair of a section's KeyValues blocks (`items` in the stored JSON)."""
    return [row for block in section.get("blocks", []) if block.get("kind") == "kv" for row in block.get("items") or []]


def rows_named(section, key):
    return [row for row in pairs_of(section) if row and row[0] == key]


sections = doc.get("sections", [])
campaign = next((s for s in sections if s.get("title") == "Campaign"), {})
show("589 access-certification run", queued_status=status, id=run.get("id"), status=run.get("status"),
     sha256=run.get("sha256"), page_one=(sections[0].get("title"), sections[0].get("sealed")) if sections else None,
     page_one_data_as_of=bool(sections and rows_named(sections[0], "Data as of")),
     campaign_sealed=campaign.get("sealed"), campaign_keys=[row[0] for row in pairs_of(campaign)],
     campaign_data_as_of=bool(rows_named(campaign, "Data as of")))
