source /private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad/walk/lib.sh
SHOTS=/private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad/shots/rejoin
scopes() {  # scopes <clusters...>: every persona's (policy, scope) on each
  for u in kubeadmin jane.smith developer test-user-002; do
    printf '  %-14s' "$u"; api_as "$u" /api/whoami | python3 -c 'import json,sys
v=json.load(sys.stdin)["visibility"]["clusters"]; print("  ".join(f"{c}={v.get(c,{}).get(\"scope\")}" for c in sys.argv[1:]))' "$@"
  done
}
pagecheck() {  # pagecheck <tag> <json: {user: [full clusters]}> <clusters...>: the fixed Step 6 check, one fresh page each
  tag=$1; wide=$2; shift 2
  "$PY" - "$tag" "$wide" "$SHOTS" "$@" <<'PY'
import json, sys
from playwright.sync_api import sync_playwright
tag, wide, shots, clusters = sys.argv[1], json.loads(sys.argv[2]), sys.argv[3], sys.argv[4:]
HOST, FULL = "The host decides your view of this cluster.", "This cluster's own RBAC gives you the full view."
OWN = "This cluster's own RBAC shows your own rows, or could not be asked."
with sync_playwright() as p:
    browser = p.chromium.launch()
    for user, full in wide.items():
        for cluster in clusters:
            want = HOST if cluster == "dashboard" else FULL if cluster in full else OWN
            context = browser.new_context(extra_http_headers={"X-Forwarded-User": user}, viewport={"width": 1440, "height": 900}, color_scheme="dark")
            page = context.new_page()
            page.goto(f"http://127.0.0.1:18080/#page=home&cluster={cluster}")
            try:
                page.wait_for_function("(t) => (document.getElementById('scope-why') || {}).textContent === t", arg=want, timeout=15000)
                print("  ok ", user, cluster, want)
            except Exception:
                print("  BAD", user, cluster, page.evaluate("() => (document.getElementById('scope-why') || {}).textContent"))
            if cluster == "shared-qa" and user in ("kubeadmin", "developer"):
                page.screenshot(path=f"{shots}/{tag}-{user}-shared-qa.png", clip={"x": 0, "y": 0, "width": 1440, "height": 260})
            context.close()
    ctx = browser.new_context(extra_http_headers={"X-Forwarded-User": "kubeadmin"}, viewport={"width": 1440, "height": 1100}, color_scheme="dark")
    pg = ctx.new_page(); pg.goto("http://127.0.0.1:18080/#page=clusters"); pg.wait_for_timeout(4000)
    pg.screenshot(path=f"{shots}/{tag}-cluster-configurations.png", full_page=True)
    browser.close()
PY
}
jwt_exp() { python3 -c '
import base64, json, sys, datetime
t = sys.stdin.read().strip().split(".")
p = json.loads(base64.urlsafe_b64decode(t[1] + "=" * (-len(t[1]) % 4)))
print("sub", p.get("sub"), "| exp", datetime.datetime.fromtimestamp(p["exp"], datetime.timezone.utc).isoformat() if "exp" in p else "NONE (no expiry)")'; }

echo "== A. re-create mock-sar through the tab (runtime Secret, the tab-made join)"
TOKEN=$(awk '/^  token:/{gsub(/"/,"",$2); print $2; exit}' local-development/mock-app/fixtures/reference.yaml)
CA=$(oc get secret mock-ca -n "$NS" -o jsonpath='{.data.tls\.crt}')
printf '{"name": "mock-sar", "server": "https://mock-openshift:6443", "credential": {"kind": "bearerToken", "token": "%s"}, "tls": {"mode": "caData", "caData": "%s"}}' "$TOKEN" "$CA" \
  | oc exec -i -n "$NS" "$(pod)" -c dashboard -- curl -s -X POST -H 'X-Forwarded-User: kubeadmin' -H 'Content-Type: application/json' --data-binary @- http://127.0.0.1:8080/api/clusterconfigs | head -c 200; echo
for _ in $(seq 1 60); do resolved mock-sar | grep -q . && break; sleep 10; done
resolved mock-sar | sed -E 's/.*(cycle=[0-9]+ cluster=[^ ]+).*(visibility=[^ ]+ identity=[^ ]+ enabled=[^ ]+).*/  \1 \2/'
echo "== B. shared-qa expired (intentional): its token"
oc get secret gsd-cluster-shared-qa -n "$NS" -o json | python3 -c 'import base64,json,sys; print(json.loads(base64.b64decode(json.load(sys.stdin)["data"]["config"]))["bearerToken"])' | jwt_exp
echo "== B. scopes through the API"
scopes dashboard shared-rnd shared-qa mock-sar
echo "== B. the fixed Step 6 page check (one fresh page per reader and cluster)"
oc port-forward -n "$NS" "$(pod)" 18080:8080 >/dev/null & PF=$!; sleep 3
pagecheck expired '{"kubeadmin": ["shared-rnd", "mock-sar"], "jane.smith": ["shared-rnd"], "developer": ["mock-sar"], "test-user-002": []}' dashboard shared-rnd shared-qa mock-sar
echo "== C. Step 11: rejoin shared-qa with a long-lived token"
oc apply -n group-sync-operator -f - <<'YAML'
apiVersion: v1
kind: Secret
metadata:
  name: shared-qa-poller-token
  annotations:
    kubernetes.io/service-account.name: shared-qa-poller
type: kubernetes.io/service-account-token
YAML
until [ -n "$(oc get secret shared-qa-poller-token -n group-sync-operator -o jsonpath='{.data.token}')" ]; do sleep 2; done
oc get secret shared-qa-poller-token -n group-sync-operator -o jsonpath='{.data.token}' | base64 -d | jwt_exp
c=$(resolved shared-qa | sed -E 's/.* cycle=([0-9]+) .*/\1/')
printf '{"token": "%s"}' "$(oc get secret shared-qa-poller-token -n group-sync-operator -o jsonpath='{.data.token}' | base64 -d)" \
  | oc exec -i -n "$NS" "$(pod)" -c dashboard -- curl -s -X PUT -H 'X-Forwarded-User: kubeadmin' -H 'Content-Type: application/json' --data-binary @- http://127.0.0.1:8080/api/clusterconfigs/shared-qa/credential | head -c 200; echo
for _ in $(seq 1 60); do n=$(resolved shared-qa | sed -E 's/.* cycle=([0-9]+) .*/\1/'); [ -n "$n" ] && [ "$n" != "$c" ] && break; sleep 10; done
resolved shared-qa | sed -E 's/.*(cycle=[0-9]+ cluster=[^ ]+).*(visibility=[^ ]+ identity=[^ ]+ enabled=[^ ]+).*/  \1 \2/'
sleep 70
echo "  poller after the rejoin: $(oc logs -n "$NS" "$(pod)" -c dashboard --since=70s | grep -E 'polled shared-qa|shared-qa.*auth_failed' | tail -2 | cut -c1-160)"
echo "== C. scopes through the API"
scopes shared-qa
echo "== C. the page check after the rejoin"
pagecheck rejoined '{"kubeadmin": ["shared-rnd", "shared-qa", "mock-sar"], "jane.smith": ["shared-rnd", "shared-qa"], "developer": ["mock-sar"], "test-user-002": []}' shared-qa
kill "$PF"
echo "== D. mock-sar removed again"
oc exec -n "$NS" "$(pod)" -c dashboard -- curl -s -o /dev/null -w "  DELETE mock-sar: %{http_code}\n" -X DELETE -H 'X-Forwarded-User: kubeadmin' http://127.0.0.1:8080/api/clusterconfigs/mock-sar
echo "== E. the e2e walk, again"
cd local-development && GSD_UI_PASSWORD=$(cat ~/.crc/machines/crc/kubeadmin-password) ./e2e-walk/run_walk.sh \
  --base https://group-sync-dashboard.apps-crc.testing --login-user kubeadmin --out "$WALK/../e2e/2026-09-24_d2b-rejoined" 2>&1 | grep -E "steps passed|extra steps|reports pass|e2e exit|FAIL" ; echo "  e2e exit ${PIPESTATUS[0]}"
