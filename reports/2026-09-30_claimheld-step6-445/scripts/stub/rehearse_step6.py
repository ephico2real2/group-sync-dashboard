"""Offline rehearsal of SPEC_S4c §3.12 step 6's coordinator, INSIDE the dashboard image, against a fake API server.

Run by scripts/offline_proofs.sh as `podman run -i … <the dashboard image> python3.14 /walk/rehearse_step6.py
<scenario> < <the coordinator extracted from the spec>`: the program arrives on stdin exactly as `oc exec -i …
python3.14 -` delivers it on the lab, and runs under the image's own python3.14 and its own `gsd`. What differs from
the lab is only what the pod supplies: the ServiceAccount namespace file and GSD_CONFIG are mounted by the proof, and
the host cluster in that config is this fake — the Lease resource of one namespace on 127.0.0.1, the API conventions'
CAS enforced (a POST of an existing name and a PUT with a stale resourceVersion answer 409), every request logged.
Standard library only.

Scenarios — the Lease `gsd-fleet-88fa0d759f845b47` before the coordinator starts:
  absent   the lab today (phase 1's baseline): A's claim creates it
  free     the lab after steps 2-5 (the spec's premise): held by nobody, so A's claim is a PUT
  held     the running pod holds it (6.0 skipped): the coordinator must abort without writing

Prints the coordinator's own stdout/stderr as they come, then `# fake API:` lines — every request, and the Lease as
it ends — and exits with the coordinator's exit code.
"""
import json
import subprocess
import sys
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

NS, NAME, PORT = "group-sync-dashboard", "gsd-fleet-88fa0d759f845b47", 18443
LEASES = f"/apis/coordination.k8s.io/v1/namespaces/{NS}/leases"
lock, objects, log, serial = threading.Lock(), {}, [], [1000]


def micro(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def seed(scenario: str) -> None:
    base = {"apiVersion": "coordination.k8s.io/v1", "kind": "Lease",
            "metadata": {"name": NAME, "namespace": NS, "resourceVersion": "1000",
                         "labels": {"groupsync-dashboard.io/lease-type": "fleet-account"},
                         "annotations": {"groupsync-dashboard.io/account": "developer"}}}
    if scenario == "free":
        objects[NAME] = {**base, "spec": {"holderIdentity": "", "leaseDurationSeconds": 195}}
    elif scenario == "held":
        now = micro(datetime.now(UTC))
        objects[NAME] = {**base, "spec": {"holderIdentity": "group-sync-dashboard-pod", "leaseDurationSeconds": 195,
                                          "acquireTime": now, "renewTime": now}}
    elif scenario != "absent":
        sys.exit(f"unknown scenario {scenario!r}")


class Api(BaseHTTPRequestHandler):
    def log_message(self, *args):          # the proof logs each request itself, below
        pass

    def reply(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        log.append(f"{self.command} {self.path} -> {code}")

    def status(self, code: int, reason: str) -> None:
        self.reply(code, {"kind": "Status", "apiVersion": "v1", "status": "Failure", "reason": reason, "code": code})

    def body(self) -> dict:
        return json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")

    def do_GET(self):
        with lock:
            if self.path == f"{LEASES}/{NAME}" and NAME in objects:
                return self.reply(200, objects[NAME])
            return self.status(404, "NotFound")

    def do_POST(self):
        with lock:
            obj = self.body()
            if self.path != LEASES or obj.get("metadata", {}).get("name") != NAME:
                return self.status(404, "NotFound")
            if NAME in objects:
                return self.status(409, "AlreadyExists")
            serial[0] += 1
            obj["metadata"]["resourceVersion"] = str(serial[0])
            objects[NAME] = obj
            return self.reply(201, obj)

    def do_PUT(self):
        with lock:
            obj = self.body()
            if self.path != f"{LEASES}/{NAME}" or NAME not in objects:
                return self.status(404, "NotFound")
            if obj.get("metadata", {}).get("resourceVersion") != objects[NAME]["metadata"]["resourceVersion"]:
                return self.status(409, "Conflict")
            serial[0] += 1
            obj["metadata"]["resourceVersion"] = str(serial[0])
            objects[NAME] = obj
            return self.reply(200, obj)

    do_DELETE = do_PATCH = lambda self: self.status(405, "MethodNotAllowed")   # step 6 never sends either


seed(sys.argv[1])
server = ThreadingHTTPServer(("127.0.0.1", PORT), Api)
threading.Thread(target=server.serve_forever, daemon=True).start()
program = sys.stdin.read()                 # the coordinator, as `oc exec -i` delivers it
rc = subprocess.run([sys.executable, "-"], input=program, text=True).returncode
server.shutdown()
print("# fake API: every request, in order:")
for line in log:
    print(f"#   {line}")
lease = objects.get(NAME)
print("# fake API: the Lease at the end: " + ("absent" if lease is None else json.dumps(
    {"holderIdentity": lease["spec"].get("holderIdentity"), "resourceVersion": lease["metadata"]["resourceVersion"],
     "annotations": lease["metadata"].get("annotations")}, sort_keys=True)))
print(f"# coordinator exit code: {rc}")
sys.exit(rc)
