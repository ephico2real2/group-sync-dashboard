source /private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad/walk/lib.sh
TOKEN=$(awk '/^  token:/{gsub(/"/,"",$2); print $2; exit}' local-development/mock-app/fixtures/reference.yaml)
CA=$(oc get secret mock-ca -n "$NS" -o jsonpath='{.data.tls\.crt}')
[ -n "$TOKEN" ] && [ -n "$CA" ] || { echo "token or CA empty"; exit 1; }
create() {  # create <name> [<extra JSON members>]
  printf '{"name": "%s", "server": "https://mock-openshift:6443", "credential": {"kind": "bearerToken", "token": "%s"}, "tls": {"mode": "caData", "caData": "%s"}%s}' "$1" "$TOKEN" "$CA" "${2:-}" \
    | oc exec -i -n "$NS" "$(pod)" -c dashboard -- curl -s -X POST -H 'X-Forwarded-User: kubeadmin' \
        -H 'Content-Type: application/json' --data-binary @- http://127.0.0.1:8080/api/clusterconfigs | head -c 300; echo
}
create mock-sar
create mock-none ', "identity": "none"'
for s in mock-sar mock-none; do for k in visibility identity; do printf '%s %s=' "$s" "$k"; oc get secret "gsd-cluster-$s" -n "$NS" -o jsonpath="{.data.$k}" | base64 -d; echo; done; done
echo "== waiting for discovery to resolve mock-sar"
for _ in $(seq 1 60); do resolved mock-sar | grep -q . && break; sleep 10; done
resolved mock-sar; resolved mock-none
echo "== developer whoami (mock-sar, mock-none)"
api_as developer /api/whoami | python3 -c 'import json, sys
v = json.load(sys.stdin)["visibility"]["clusters"]
for c in ("mock-sar", "mock-none"): print(" ", c, v.get(c, {}).get("policy"), v.get(c, {}).get("identity"), v.get(c, {}).get("scope"))'
printf 'developer /api/clusters/mock-none/groups: '; code_as developer /api/clusters/mock-none/groups; echo
