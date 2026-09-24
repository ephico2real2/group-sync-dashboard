source /private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad/walk/lib.sh
ROOT_CA=$(oc get configmap kube-root-ca.crt -n "$NS" -o jsonpath='{.data.ca\.crt}' | base64 | tr -d '\n')
set_trust() {
  python3 - "$@" <<'PY'
import base64, json, subprocess, sys
s = json.loads(subprocess.run(["oc", "get", "secret", "gsd-cluster-shared-qa", "-n", "group-sync-dashboard", "-o", "json"],
                              check=True, capture_output=True, text=True).stdout)
config = json.loads(base64.b64decode(s["data"]["config"]))
config["tlsClientConfig"] = {"caData": sys.argv[1]}
s["data"]["config"] = base64.b64encode(json.dumps(config, separators=(",", ":")).encode()).decode()
if len(sys.argv) > 2:
    s["data"]["server"] = base64.b64encode(sys.argv[2].encode()).decode()
subprocess.run(["oc", "replace", "-f", "-"], input=json.dumps(s), check=True, capture_output=True, text=True)
PY
}
cycle_of() { resolved shared-qa | sed -E 's/.* cycle=([0-9]+) .*/\1/'; }
settle() {
  before=$1; for _ in $(seq 1 45); do now=$(cycle_of); [ -n "$now" ] && [ "$now" != "$before" ] && break; sleep 10; done
  resolved shared-qa | sed -E 's/.*(cycle=[0-9]+).*(tls=[^ ]+).*/  resolved \1 \2/'
  printf '  kubeadmin scope: '; api_as kubeadmin /api/whoami | python3 -c 'import json,sys; print(json.load(sys.stdin)["visibility"]["clusters"].get("shared-qa",{}).get("scope"))'
  printf '  last tier warning: '; oc logs -n "$NS" "$(pod)" -c dashboard --since=90s | grep 'gsd.kube shared-qa: visibility tier' | tail -1 | sed -E 's/.*indeterminate \(([^)]*)\).*/\1/'; echo
}
echo "== the in-cluster URL by another name (the refused kubernetes.default.svc is the host's convention)"
c=$(cycle_of); set_trust "$ROOT_CA" https://kubernetes.default.svc.cluster.local; settle "$c"
printf '  served server: '; oc get secret gsd-cluster-shared-qa -n "$NS" -o jsonpath='{.data.server}' | base64 -d; echo
echo "== restore exactly as the spec writes it (the intentionally expired token included)"
c=$(cycle_of)
python3 -c "import json,sys; s=json.load(open(sys.argv[1])); m=s['metadata']; [m.pop(k, None) for k in ('resourceVersion','uid','creationTimestamp','managedFields')]; print(json.dumps(s))" "$WALK/shared-qa.json" | oc replace -f -
oc delete secret shared-qa-poller-token -n group-sync-operator
settle "$c"
oc get secret gsd-cluster-shared-qa -n "$NS" -o json | python3 -c '
import base64, json, sys, datetime
d = json.load(sys.stdin)["data"]; t = json.loads(base64.b64decode(d["config"]))["bearerToken"].split(".")
p = json.loads(base64.urlsafe_b64decode(t[1] + "=" * (-len(t[1]) % 4)))
print("  restored token exp:", datetime.datetime.fromtimestamp(p["exp"], datetime.timezone.utc).isoformat(), "| server:", base64.b64decode(d["server"]).decode())'
oc get secret shared-qa-poller-token -n group-sync-operator -o name 2>&1 | head -1
