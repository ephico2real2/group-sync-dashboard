#!/bin/bash
# shots.sh <label>: the Access granted page as the running pod renders it (loopback through a port-forward, the
# viewer header the proxy would set), captured to ${W}/shots/<label>-*.png. Read-only.
set -uo pipefail
source "$(dirname "$0")/lib.sh"
label="${1:?usage: shots.sh <label>}"; mkdir -p "${W}/shots"
PY=/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/.venv/bin/python
oc port-forward -n "$NS" "$(pod)" 18082:8080 >/dev/null 2>&1 & PF=$!; sleep 3
"$PY" - "${W}/shots" "$label" <<'PY'
import sys
from playwright.sync_api import sync_playwright
out, label = sys.argv[1], sys.argv[2]
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(extra_http_headers={"X-Forwarded-User": "kubeadmin"}, viewport={"width": 1440, "height": 900}, color_scheme="dark")
    page = ctx.new_page()
    page.goto("http://127.0.0.1:18082/#page=home&cluster=dashboard"); page.wait_for_timeout(1500)
    page.locator("button[data-nav='bindings']").click(); page.wait_for_selector("text=grant nobody", timeout=20000); page.wait_for_timeout(2000)
    tiles = page.evaluate("() => Object.fromEntries([...document.querySelectorAll('.kpis.mt-0 .kpi')].map(k => [k.querySelector('.label').innerText.trim(), k.querySelector('.value').innerText.trim()]))")
    print("   access granted tiles:", tiles)
    page.screenshot(path=f"{out}/{label}-access-granted.png", clip={"x": 0, "y": 0, "width": 1440, "height": 560})
    unm = page.locator("section", has=page.locator("h2", has_text="Unmanaged")).first
    if unm.count():
        unm.scroll_into_view_if_needed(); page.wait_for_timeout(500); unm.screenshot(path=f"{out}/{label}-unmanaged-section.png")
        print("   unmanaged section:", " ".join(unm.locator("h2").first.inner_text().split()))
    sel = page.locator("select#binding-filter, select[name='bindingFilter']").first
    if sel.count():
        sel.select_option("built_in"); page.wait_for_timeout(1500)
        page.screenshot(path=f"{out}/{label}-built-in-filter.png", clip={"x": 0, "y": 0, "width": 1440, "height": 900})
    b.close()
PY
kill $PF 2>/dev/null; wait $PF 2>/dev/null; ls -1 "${W}/shots" | grep "^${label}-"
