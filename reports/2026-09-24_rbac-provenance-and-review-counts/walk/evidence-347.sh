# #347 on the lab: a hand-made grant on an operator-synced group is counted under review, then removed.
# The lab's only unmanaged grant was the chart's own auditor binding, which #312 labelled, so the lab
# has none; this plants one (disposable, a namespace of its own), captures, and removes it again.
source /private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad/walk/lib.sh
SHOTS=/private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad/shots/fixes
EV=gsd-evidence-347; GROUP=app-ocp-rbac-groupsync-ns-auditor

counts() {  # counts <label>
  echo "-- $1"
  api_as kubeadmin /api/clusters/dashboard/bindings/findings | python3 -c 'import json,sys
d = json.load(sys.stdin); c = d["counts"]; review = c.get("dangling",0) + c.get("unresolved",0) + c.get("unmanaged",0)
print("   dashboard findings: total", d["total"], "| ok", c.get("ok",0), "| dangling", c.get("dangling",0), "| unresolved", c.get("unresolved",0),
      "| unmanaged", c.get("unmanaged",0), "| built-in", c.get("built_in",0), "| ok+review+built-in", c.get("ok",0) + review + c.get("built_in",0))'
  api_as kubeadmin /api/clusters | python3 -c 'import json,sys
for c in json.load(sys.stdin):
    if c["id"] in ("dashboard", "shared-qa", "shared-rnd"):
        print("   /api/clusters", c["id"], "dangling", c.get("dangling_bindings"), "unresolved", c.get("unresolved_bindings"), "unmanaged", c.get("unmanaged_bindings"))'
}
wait_refresh() {  # wait_refresh <expected count>: a dashboard binding refresh reporting it, newer than the call
  local seen; seen=$(oc logs -n "$NS" "$(pod)" -c dashboard | grep -c "refreshed $1 group bindings for dashboard")
  for _ in $(seq 1 48); do
    [ "$(oc logs -n "$NS" "$(pod)" -c dashboard | grep -c "refreshed $1 group bindings for dashboard")" -gt "$seen" ] && break; sleep 15
  done
  echo "   refresh: $(oc logs -n "$NS" "$(pod)" -c dashboard | grep "refreshed $1 group bindings for dashboard" | tail -1 | cut -c1-100)"
}

echo "== baseline"
counts "before the grant"
echo "== the hand-made grant"
oc create namespace "$EV"
oc create rolebinding evidence-347-hand-made -n "$EV" --clusterrole=view --group="$GROUP"
oc get rolebinding evidence-347-hand-made -n "$EV" -o jsonpath='   labels: {.metadata.labels}{"\n"}   subject: {.subjects[0].kind}/{.subjects[0].name}{"\n"}'
wait_refresh 206
echo "   log: $(oc logs -n "$NS" "$(pod)" -c dashboard | grep 'UNMANAGED GRANT DISCOVERED' | grep evidence-347 | tail -1 | cut -c1-160)"
counts "with the grant"

echo "== the pages"
oc port-forward -n "$NS" "$(pod)" 18082:8080 >/dev/null & PF=$!; sleep 3
"$PY" - "$SHOTS" <<'PY'
import sys
from playwright.sync_api import sync_playwright
out = sys.argv[1]
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(extra_http_headers={"X-Forwarded-User": "kubeadmin"}, viewport={"width": 1440, "height": 900}, color_scheme="dark")
    page = ctx.new_page()
    page.goto("http://127.0.0.1:18082/#page=home&cluster=dashboard"); page.wait_for_timeout(1500)
    page.locator("button[data-nav='bindings']").click(); page.wait_for_selector("text=grant nobody", timeout=20000); page.wait_for_timeout(1500)
    tiles = page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('.kpis.mt-0 .kpi')].map(k => [k.querySelector('.label').innerText.trim(), k.querySelector('.value').innerText.trim()]))""")
    print("   access granted tiles:", tiles)
    page.screenshot(path=f"{out}/347-access-granted-with-unmanaged.png", clip={"x": 0, "y": 0, "width": 1440, "height": 520})
    unm = page.locator("section.card", has=page.locator("h2", has_text="Unmanaged")).first
    print("   unmanaged section:", " ".join(unm.locator("h2").inner_text().split()))
    unm.scroll_into_view_if_needed(); unm.screenshot(path=f"{out}/347-unmanaged-section.png")
    page.click("#tab-overview"); page.wait_for_selector("section.tile[data-cluster='dashboard']", timeout=20000); page.wait_for_timeout(1500)
    for cid in ("dashboard", "shared-qa", "shared-rnd"):
        t = page.locator(f"section.tile[data-cluster='{cid}']")
        if t.count():
            v = t.locator(".tk > span", has=page.locator(".lab", has_text="Bindings to review")).locator(".v").inner_text().strip()
            print(f"   overview tile {cid}: Bindings to review {v}")
    page.locator("section.tile[data-cluster='dashboard']").screenshot(path=f"{out}/347-overview-tile.png")
    page.click("#tab-kpi"); page.wait_for_selector(".kpi-page .kband .kpi", timeout=20000); page.wait_for_timeout(1500)
    rv = page.locator('.kpi-page .kpi[data-kpi="review"]')
    print("   kpi to review:", " ".join(rv.inner_text().split()))
    page.locator("section.kpi-page", has=page.locator("h2", has_text="Access posture")).screenshot(path=f"{out}/347-kpi-posture-with-unmanaged.png")
    b.close()
PY
kill "$PF"

echo "== removing the grant"
oc delete namespace "$EV" --wait=true
wait_refresh 205
counts "after removing it"
