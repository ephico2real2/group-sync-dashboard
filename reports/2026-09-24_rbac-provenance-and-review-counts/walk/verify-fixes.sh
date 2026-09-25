source /private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad/walk/lib.sh
SHOTS=/private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad/shots/fixes
echo "== #312 the chart's auditor binding, and the auditor tier with its negative control"
crb=$(oc get clusterrolebinding -o name | grep 'group-sync-dashboard-ra-' | head -1)
oc get "$crb" -o jsonpath='{.metadata.name}: config-source={.metadata.labels.rbac\.ocp\.io/config-source}{"\n"}'
printf 'member of app-ocp-rbac-groupsync-ns-auditor: '; oc auth can-i list clusterrolebindings --as=someauditor --as-group=app-ocp-rbac-groupsync-ns-auditor --as-group=system:authenticated
printf 'no auditor group (negative control):        '; oc auth can-i list clusterrolebindings --as=someauditor --as-group=system:authenticated
for _ in $(seq 1 40); do oc logs -n "$NS" "$(pod)" -c dashboard | grep -q "refreshed .* group bindings for dashboard" && break; sleep 15; done
echo "binding refresh: $(oc logs -n "$NS" "$(pod)" -c dashboard | grep -m1 'refreshed .* group bindings for dashboard' | cut -c1-110)"
echo "UNMANAGED GRANT DISCOVERED for the -ra- binding since this pod started: $(oc logs -n "$NS" "$(pod)" -c dashboard | grep 'UNMANAGED GRANT DISCOVERED' | grep -c 'group-sync-dashboard-ra-')"
api_as kubeadmin /api/clusters | python3 -c 'import json,sys
for c in json.load(sys.stdin): print("  ", c["id"], "dangling", c.get("dangling_bindings"), "unresolved", c.get("unresolved_bindings"), "unmanaged", c.get("unmanaged_bindings"))'
echo "== #347 the Access granted counts for dashboard"
api_as kubeadmin /api/clusters/dashboard/bindings/findings | python3 -c 'import json,sys
d = json.load(sys.stdin); c = d["counts"]; review = c.get("dangling",0) + c.get("unresolved",0) + c.get("unmanaged",0)
print("   total", d["total"], "| ok", c.get("ok"), "| need review", review, "| built-in", c.get("built_in"), "| sum", c.get("ok",0) + review + c.get("built_in",0))'
echo "== the pages (#346 Logins, #347 Access granted and KPI)"
oc port-forward -n "$NS" "$(pod)" 18082:8080 >/dev/null & PF=$!; sleep 3
"$PY" - "$SHOTS" <<'PY'
import sys
from playwright.sync_api import sync_playwright
out = sys.argv[1]
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(extra_http_headers={"X-Forwarded-User": "kubeadmin"}, viewport={"width": 1440, "height": 900}, color_scheme="dark")
    page = ctx.new_page()
    page.goto("http://127.0.0.1:18082/#page=logins&cluster=dashboard")
    page.wait_for_selector("text=Login attempts", timeout=20000); page.wait_for_timeout(2500)
    body = " ".join(page.locator("body").inner_text().split())
    for phrase in ("oldest audit file still on the control-plane nodes", "dies with its pod", "Node", "control-plane node whose audit file"):
        print(f"   logins: {phrase!r}: {'present' if phrase in body else 'absent'}")
    page.screenshot(path=f"{out}/346-logins.png", full_page=True)
    page.goto("http://127.0.0.1:18082/#page=home&cluster=dashboard"); page.wait_for_timeout(1500)
    page.locator("button[data-nav='bindings']").click(); page.wait_for_selector("text=grant nobody", timeout=20000); page.wait_for_timeout(1500)
    tiles = page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('.kpis.mt-0 .kpi')].map(k => [k.querySelector('.label').innerText.trim(), k.querySelector('.value').innerText.trim()]))""")
    print("   access granted tiles:", tiles)
    page.screenshot(path=f"{out}/347-access-granted.png", clip={"x": 0, "y": 0, "width": 1440, "height": 520})
    page.click("#tab-kpi"); page.wait_for_selector(".kpi-page .kband .kpi", timeout=20000); page.wait_for_timeout(1500)
    rv = page.locator('.kpi-page .kpi[data-kpi="review"]')
    print("   kpi to review:", " ".join(rv.inner_text().split()))
    page.screenshot(path=f"{out}/347-kpi.png", clip={"x": 0, "y": 0, "width": 1440, "height": 700})
    b.close()
PY
kill "$PF"
