source /private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad/walk/lib.sh
# The token's expiry, read from its JWT payload; the token itself is never printed.
oc get secret gsd-cluster-shared-qa -n "$NS" -o jsonpath='{.data.token}' | base64 -d | python3 -c '
import base64, json, sys, datetime
t = sys.stdin.read().strip(); parts = t.split(".")
if len(parts) != 3: print("token is not a JWT (len", len(t), ")"); sys.exit()
p = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
exp = p.get("exp"); iat = p.get("iat")
fmt = lambda s: datetime.datetime.fromtimestamp(s, datetime.timezone.utc).isoformat() if s else None
print("sub", p.get("sub"), "| iat", fmt(iat), "| exp", fmt(exp))'
echo "first 401 for shared-qa in this pod: $(oc logs -n "$NS" "$(pod)" -c dashboard | grep 'shared-qa' | grep -m1 '401' | cut -c1-24)"
# D5, one fresh page per (user, cluster): no hash-only navigation, so no stale text can match.
oc port-forward -n "$NS" "$(pod)" 18080:8080 >/dev/null & PF=$!; sleep 3
"$PY" - <<'PY'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch()
    for user in ("kubeadmin", "jane.smith"):
        for cluster in ("shared-rnd", "shared-qa"):
            ctx = browser.new_context(extra_http_headers={"X-Forwarded-User": user})
            page = ctx.new_page()
            page.goto(f"http://127.0.0.1:18080/#page=home&cluster={cluster}")
            page.wait_for_function("() => (document.getElementById('scope-why') || {}).textContent", timeout=15000)
            page.wait_for_timeout(1500)
            print(user, cluster, "->", page.evaluate("() => document.getElementById('scope-why').textContent"))
            ctx.close()
    browser.close()
PY
kill "$PF"
