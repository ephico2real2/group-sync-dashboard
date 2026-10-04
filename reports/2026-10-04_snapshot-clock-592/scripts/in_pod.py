"""Runs INSIDE the report pod: SPEC_F7 §5 steps 1 and 2 on 5.1.0 (#592, #607). Reads the viewer and a dashboard-minted
ticket and the phase from stdin, so no secret is on a command line, and prints one JSON line per fact. Nothing secret is printed.

  1. One snapshot, two clocks, one hash (phase `pair`): compliance-snapshot and login-activity on `dashboard`, each
     run twice three minutes apart. Pass: equal snapshot stamps and equal sha256s. login-activity's Window `To` equals the stamp to the
     second, and the two runs' "Generated at" differ by about three minutes. A pair that straddles a new copy is run
     again (the spec's rule).
  2. #607 on `mock-trusted` (phases `first`, `stamp`, `second`): compliance-snapshot on one snapshot, then on the next
     one, and a report-diff of the two.
     Pass: "No change", or only data rows changed (none is "Last poll" or "last read"). Page one of each run still shows
     the "Last poll" instant and the capture note's "(last read …)"."""
import json, pathlib, ssl, sys, time, urllib.error, urllib.request

# One phase per call, each with a fresh ticket from run.sh: the dashboard mints tickets for 300 s
# (reportingTicketTtlSeconds), shorter than a retried pair or a wait for the next snapshot copy.
viewer, ticket, phase, arg = (sys.stdin.readline().strip() for _ in range(4))
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE  # loopback only
H = {"X-Forwarded-User": viewer, "X-GSD-Report-Ticket": ticket, "Content-Type": "application/json"}
ART = pathlib.Path("/artifacts")


def show(check, **facts):
    print(json.dumps({"t": time.strftime("%H:%M:%SZ", time.gmtime()), "check": check, **facts}), flush=True)


def call(method, path, body=None):
    req = urllib.request.Request("https://127.0.0.1:8443" + path, method=method, headers=H,
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def finished(report, cluster, params=None):
    status, run = call("POST", "/report/api/runs", {"report": report, "cluster": cluster, "params": params or {},
                                                    "formats": ["html"]})
    assert status == 202, (status, run)
    for _ in range(150):
        _, run = call("GET", f"/report/api/runs/{run['id']}")
        if run.get("status") in ("done", "failed"):
            return run
        time.sleep(2)
    return run


def doc(run):
    return json.loads((ART / run["id"] / "report.json").read_text())


def kv(section_doc, section, block, key):
    for s in section_doc["sections"]:
        if s["title"] == section:
            for b in s["blocks"]:
                if b.get("kind") == "kv" and b["title"] == block:
                    return dict((k, v) for k, v in b["items"]).get(key)


def page_one(d):
    rows = {}
    for b in d["sections"][0]["blocks"]:
        if b.get("kind") == "kv":
            rows.update({k: v for k, v in b["items"]})
    notes = [b["text"] for b in d["sections"][0]["blocks"] if b.get("kind") == "note"]
    return rows, notes


def snapshot_stamp():
    return call("GET", "/report/api/snapshot")[1].get("stamp")


if phase == "stamp":                                  # the current snapshot copy, for run.sh's wait
    print(snapshot_stamp())
elif phase == "pair":                                 # step 1, one attempt; exit 3 when it straddles a copy
    first = {r: finished(r, "dashboard") for r in ("compliance-snapshot", "login-activity")}
    time.sleep(180)
    second = {r: finished(r, "dashboard") for r in ("compliance-snapshot", "login-activity")}
    if not all(first[r]["snapshot_stamp"] == second[r]["snapshot_stamp"] for r in first):
        show("1 a pair straddled a new copy; run again",
             stamps={r: [first[r]["snapshot_stamp"], second[r]["snapshot_stamp"]] for r in first})
        sys.exit(3)
    for r in first:
        a, b = first[r], second[r]
        da, db = doc(a), doc(b)
        fact = {"report": r, "runs": [a["id"], b["id"]], "stamps": [a["snapshot_stamp"], b["snapshot_stamp"]],
                "sha256": [a["sha256"], b["sha256"]], "same_sha256": a["sha256"] == b["sha256"],
                "generated_at": [page_one(da)[0].get("Generated at (UTC)"), page_one(db)[0].get("Generated at (UTC)")]}
        if r == "login-activity":
            fact["window_to"] = [kv(da, "Summary", "Window", "To"), kv(db, "Summary", "Window", "To")]
            fact["to_equals_stamp_to_the_second"] = all(t == st[:19] + "Z" for t, st in zip(fact["window_to"], fact["stamps"]))
        show("1 one snapshot, two clocks, one hash", **fact)
elif phase == "first":                                # step 2: the run on this snapshot; prints its id and stamp
    c1 = finished("compliance-snapshot", "mock-trusted")
    print(json.dumps({"id": c1["id"], "stamp": c1["snapshot_stamp"]}))
elif phase == "second":                               # step 2: the run on the next copy, and the diff of the two
    _, c1 = call("GET", f"/report/api/runs/{arg}")
    c2 = finished("compliance-snapshot", "mock-trusted")
    diff = finished("report-diff", "mock-trusted", {"base": c1["id"], "head": c2["id"]})
    dd = doc(diff) if diff.get("status") == "done" else {}
    changed = [row for sec in dd.get("sections", [])[1:] for b in sec["blocks"]
               if b.get("kind") == "table" and b["title"] == "Changes per block" for row in b["rows"]]
    p1 = [page_one(doc(c)) for c in (c1, c2)]
    show("2 #607 on mock-trusted", runs=[c1["id"], c2["id"]], stamps=[c1["snapshot_stamp"], c2["snapshot_stamp"]],
         sha256=[c1["sha256"], c2["sha256"]], diff=diff.get("id"), diff_status=diff.get("status"),
         totals=dd.get("totals"), changed_blocks=changed,
         page_one_last_poll=[rows.get("Last poll") for rows, _ in p1],
         page_one_last_read=[any("last read" in n for n in notes) for _, notes in p1])
