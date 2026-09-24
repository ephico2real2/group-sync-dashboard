source /private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad/walk/lib.sh
# Wait for the next discovery cycle after now and print shared-rnd's resolved line from it.
cycle_of() { resolved shared-rnd | sed -E 's/.* cycle=([0-9]+) .*/\1/'; }
next_cycle() {
  before=$(cycle_of); for _ in $(seq 1 90); do now=$(cycle_of); [ -n "$now" ] && [ "$now" != "$before" ] && break; sleep 10; done
  resolved shared-rnd
}
findings() { api_as kubeadmin /api/clusterconfigs | python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps([f for f in json.dumps(d).split("\"") if "shadow" in f][:5]))'; }
echo "== baseline"; resolved shared-rnd; findings
echo "== annotation removed"
oc annotate secret gsd-cluster-shared-rnd -n "$NS" groupsync-dashboard.io/token-source-
next_cycle; findings
echo "== annotation restored"
oc annotate secret gsd-cluster-shared-rnd -n "$NS" groupsync-dashboard.io/token-source=remote-lookup
next_cycle; findings
echo "== Secret deleted; waiting for the lookup to write it again"
oc delete secret gsd-cluster-shared-rnd -n "$NS"
start=$(date +%s)
until oc get secret gsd-cluster-shared-rnd -n "$NS" -o name >/dev/null 2>&1; do sleep 10; done
echo "rewritten after $(( $(date +%s) - start )) s"
for k in visibility identity; do printf '%s=' "$k"; oc get secret gsd-cluster-shared-rnd -n "$NS" -o jsonpath="{.data.$k}" | base64 -d; echo; done
next_cycle
