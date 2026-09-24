source /private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad/walk/lib.sh
oc get secret gsd-cluster-shared-qa -n "$NS" -o json > "$WALK/shared-qa.json"
rotate() {  # rotate <token>: the tab's route, the token on stdin
  printf '{"token": "%s"}' "$1" | oc exec -i -n "$NS" "$(pod)" -c dashboard -- curl -s -X PUT -H 'X-Forwarded-User: kubeadmin' \
    -H 'Content-Type: application/json' --data-binary @- http://127.0.0.1:8080/api/clusterconfigs/shared-qa/credential | head -c 200; echo
}
set_trust() {  # set_trust <base64 PEM> [<server>]: shared-qa's config trusts exactly that CA; the token is untouched
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
# DEVIATION (recorded): the durable token Secret is kept as shared-qa's credential, because the saved one expired
# 2026-09-23T01:57:12Z; the spec's name shared-qa-poller-d2b-walk becomes shared-qa-poller-token.
oc apply -n group-sync-operator -f - <<'YAML'
apiVersion: v1
kind: Secret
metadata:
  name: shared-qa-poller-token
  annotations:
    kubernetes.io/service-account.name: shared-qa-poller
type: kubernetes.io/service-account-token
YAML
sleep 5
NEW_TOKEN=$(oc get secret shared-qa-poller-token -n group-sync-operator -o jsonpath='{.data.token}' | base64 -d)
ROOT_CA=$(oc get configmap kube-root-ca.crt -n "$NS" -o jsonpath='{.data.ca\.crt}' | base64 | tr -d '\n')
CA=$(oc get secret mock-ca -n "$NS" -o jsonpath='{.data.tls\.crt}')
[ -n "$NEW_TOKEN" ] && [ -n "$ROOT_CA" ] && [ -n "$CA" ] || { echo "a credential is empty"; exit 1; }
cycle_of() { resolved shared-qa | sed -E 's/.* cycle=([0-9]+) .*/\1/'; }
settle() {  # wait for shared-qa's next resolved line, then read kubeadmin's scope on it
  before=$1; for _ in $(seq 1 90); do now=$(cycle_of); [ -n "$now" ] && [ "$now" != "$before" ] && break; sleep 10; done
  resolved shared-qa | sed -E 's/.*(cycle=[0-9]+).*(tls=[^ ]+).*/  resolved \1 \2/'
  printf '  kubeadmin scope: '; api_as kubeadmin /api/whoami | python3 -c 'import json,sys; print(json.load(sys.stdin)["visibility"]["clusters"].get("shared-qa",{}).get("scope"))'
  printf '  last warning: '; oc logs -n "$NS" "$(pod)" -c dashboard --since=90s | grep 'gsd.kube shared-qa' | tail -1 | sed -E 's/.*indeterminate \(([^)]*)\).*/\1/'; echo
}
step() { echo "== $1"; c=$(cycle_of); shift; "$@"; settle "$c"; }
step "a token that is not one"                rotate sha256~d2b-walk-not-a-token
step "a new token of the same ServiceAccount" rotate "$NEW_TOKEN"
step "a CA that does not sign api.crc.testing" set_trust "$CA"
step "the cluster's own CA bundle"            set_trust "$ROOT_CA"
step "a URL nothing answers"                  set_trust "$ROOT_CA" https://api.crc.testing:6444
step "the in-cluster URL"                     set_trust "$ROOT_CA" https://kubernetes.default.svc
# Restore the saved server and trust, with the working token (DEVIATION: the saved token is expired).
c=$(cycle_of)
NEW_TOKEN="$NEW_TOKEN" python3 -c '
import base64, json, os, sys
s = json.load(open(sys.argv[1])); m = s["metadata"]
[m.pop(k, None) for k in ("resourceVersion", "uid", "creationTimestamp", "managedFields")]
cfg = json.loads(base64.b64decode(s["data"]["config"])); cfg["bearerToken"] = os.environ["NEW_TOKEN"]
s["data"]["config"] = base64.b64encode(json.dumps(cfg, separators=(",", ":")).encode()).decode()
print(json.dumps(s))' "$WALK/shared-qa.json" | oc replace -f - && echo "== restored: saved server and trust, working token"
settle "$c"
