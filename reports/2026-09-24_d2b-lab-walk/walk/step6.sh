source /private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad/walk/lib.sh
for u in kubeadmin jane.smith developer test-user-002; do
  echo "== $u"
  api_as "$u" /api/whoami | python3 -c 'import json, sys
v = json.load(sys.stdin)["visibility"]["clusters"]
for c in ("dashboard", "shared-rnd", "shared-qa", "mock", "mock-sar"):
    print(" ", c, v.get(c, {}).get("policy"), v.get(c, {}).get("scope"))'
  for c in shared-qa mock; do
    for p in groups bindings/findings home; do printf '  %s %s: %s\n' "$c" "$p" "$(code_as "$u" "/api/clusters/$c/$p")"; done
  done
done
oc port-forward -n "$NS" "$(pod)" 18080:8080 >/dev/null & PF=$!; sleep 3
"$PY" - <<'PY'
from playwright.sync_api import sync_playwright
HOST, FULL = "The host decides your view of this cluster.", "This cluster's own RBAC gives you the full view."
OWN = "This cluster's own RBAC shows your own rows, or could not be asked."
wide = {"kubeadmin": {"shared-rnd", "shared-qa", "mock", "mock-sar"}, "jane.smith": {"shared-rnd", "shared-qa"},
        "developer": {"mock", "mock-sar"}, "test-user-002": set()}
with sync_playwright() as p:
    browser = p.chromium.launch()
    for user, full in wide.items():
        page = browser.new_context(extra_http_headers={"X-Forwarded-User": user}).new_page()
        for cluster in ("dashboard", "shared-rnd", "shared-qa", "mock", "mock-sar"):
            want = HOST if cluster == "dashboard" else FULL if cluster in full else OWN
            page.goto(f"http://127.0.0.1:18080/#page=home&cluster={cluster}")
            try:
                page.wait_for_function("(t) => (document.getElementById('scope-why') || {}).textContent === t", arg=want, timeout=15000)
                print("ok ", user, cluster, want)
            except Exception:
                print("BAD", user, cluster, page.evaluate("() => (document.getElementById('scope-why') || {}).textContent"))
    browser.close()
PY
kill "$PF"
