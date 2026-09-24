source /private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad/walk/lib.sh
oc port-forward -n "$NS" "$(pod)" 18081:8080 >/dev/null & PF=$!; sleep 3
"$PY" - <<'PY'
from playwright.sync_api import sync_playwright
out = "/private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad/shots/d5"
cases = [("kubeadmin", "shared-rnd"), ("developer", "shared-rnd"), ("kubeadmin", "shared-qa")]
with sync_playwright() as p:
    b = p.chromium.launch()
    for user, cluster in cases:
        ctx = b.new_context(extra_http_headers={"X-Forwarded-User": user}, viewport={"width": 1440, "height": 900}, color_scheme="dark")
        page = ctx.new_page()
        page.goto(f"http://127.0.0.1:18081/#page=home&cluster={cluster}")
        page.wait_for_function("() => (document.getElementById('scope-why') || {}).textContent", timeout=20000)
        page.wait_for_timeout(2000)
        text = page.evaluate("() => document.getElementById('scope-why').textContent")
        page.screenshot(path=f"{out}/{user}-{cluster}.png", clip={"x": 0, "y": 0, "width": 1440, "height": 260})
        print(user, cluster, "->", text)
        ctx.close()
    b.close()
PY
kill "$PF"
