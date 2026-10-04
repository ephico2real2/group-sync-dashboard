#!/usr/bin/env python3
"""SPEC_F4 §5 step 4, from the files run.sh saved: the Job's log (job1.log), the receiver's log (receiver.log) and the
artefact hashes read in the report pod (artifacts.jsonl). Every delivered run's event matches the Job's line for that
run, its attachment decodes to the stored html artefact, and there is one event per run. Writes receiver-cut.log,
the receiver's lines with each base64 body replaced by its length. Exit 1 on any mismatch."""
import base64, hashlib, json, pathlib, sys
here = pathlib.Path(sys.argv[1])
runs = {}
delivered = set()
for line in (here / "job1.log").read_text().splitlines():
    try:
        d = json.loads(line)
    except ValueError:
        continue
    if "delivered" in d:
        delivered.add(d["delivered"])
    elif "id" in d and "status" in d:
        runs[d["id"]] = d
arts = {a["id"]: a for a in map(json.loads, (here / "artifacts.jsonl").read_text().splitlines())}
events, cut = [], []
for line in (here / "receiver.log").read_text().splitlines():
    r = json.loads(line); events.append(r)
    att = r["body"].get("data", {}).get("attachment") or {}
    if "content_base64" in att:
        att = {**att, "content_base64": f"<{len(att['content_base64'])} base64 characters>"}
    cut.append(json.dumps({**r, "body": {**r["body"], "data": {**r["body"]["data"], "attachment": att}}}))
(here / "receiver-cut.log").write_text("\n".join(cut) + "\n")
fails = []
def check(what, ok, detail):
    print(f"{'PASS' if ok else 'FAIL'} {what}: {json.dumps(detail)}")
    if not ok: fails.append(what)
check("one delivered line per run", delivered == set(runs), {"runs": sorted(runs), "delivered": sorted(delivered)})
check("one event per run", sorted(e["body"]["id"] for e in events) == sorted(runs), [e["body"]["id"] for e in events])
for e in events:
    b, d = e["body"], e["body"]["data"]
    run = runs.get(b["id"], {})
    check(f"{b['id']} is a CloudEvent", b.get("specversion") == "1.0" and e["content_type"].startswith("application/cloudevents+json"),
          {"specversion": b.get("specversion"), "content_type": e["content_type"], "type": b.get("type")})
    check(f"{b['id']} data matches the Job's line",
          (d["run_id"], d["cluster"], d["status"], d["sha256"], d["bytes"]) == (run.get("id"), run.get("cluster"), run.get("status"), run.get("sha256"), run.get("bytes")),
          {"cluster": d["cluster"], "status": d["status"], "sha256": (d["sha256"] or "")[:12]})
    att = d.get("attachment") or {}
    got = hashlib.sha256(base64.b64decode(att.get("content_base64", ""))).hexdigest()
    check(f"{b['id']} attachment is the stored html", got == arts.get(b["id"], {}).get("html_sha256"),
          {"attached_sha256": got[:12], "stored_sha256": arts.get(b["id"], {}).get("html_sha256", "")[:12]})
print("result", {"failures": fails})
sys.exit(1 if fails else 0)
