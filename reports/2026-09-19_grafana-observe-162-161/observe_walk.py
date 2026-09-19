"""As kubeadmin: make the console's last-used project 'All Projects' (visit an all-namespaces list),
then open the Observe door URL and record (a) the Project shown, (b) the prometheus queries the panels
issue and the namespace= each carries, (c) the URL the plugin rewrites to."""
import os, sys
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright
# CONSOLE_USER / CONSOLE_PASSWORD name the console login; OBS_PATH the door path under test
C = "https://console-openshift-console.apps-crc.testing"
URL = C + os.environ.get("OBS_PATH", "/monitoring/dashboards/dashboard-k8s-resources-workloads-namespace?project-dropdown-value=group-sync-dashboard&namespace=group-sync-dashboard&type=ALL_OPTION_KEY")
S = os.path.dirname(os.path.abspath(__file__))
mode = sys.argv[1]  # "all" -> visit all-namespaces first; "gsd" -> visit ns/group-sync-dashboard first
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(ignore_https_errors=True, viewport={"width": 1440, "height": 1000}); page = ctx.new_page()
    page.goto(C + "/", wait_until="domcontentloaded"); page.wait_for_timeout(2000)
    page.click("a:has-text('developer')"); page.wait_for_selector("#inputUsername")
    page.fill("#inputUsername", os.environ["CONSOLE_USER"]); page.fill("#inputPassword", os.environ["CONSOLE_PASSWORD"]); page.click("button[type=submit]")
    page.wait_for_timeout(5000)
    prime = "/k8s/all-namespaces/pods" if mode == "all" else "/k8s/ns/group-sync-dashboard/pods"
    page.goto(C + prime, wait_until="domcontentloaded"); page.wait_for_timeout(6000)
    print("PRIMED", page.url)
    queries = []
    page.on("request", lambda r: queries.append(r.url) if "/api/prometheus" in r.url else None)
    page.goto(URL, wait_until="domcontentloaded"); page.wait_for_timeout(12000)
    print("FINAL", page.url)
    bar = page.locator("[class*=namespace-bar], .co-namespace-bar")
    print("PROJECT", bar.first.inner_text()[:60] if bar.count() else "n/a")
    print("ALERTS", [a.inner_text()[:60] for a in page.locator(".pf-v6-c-alert__title, .pf-v5-c-alert__title").all()][:4])
    seen = set()
    for q in queries:
        u = urlparse(q); ns = parse_qs(u.query).get("namespace", ["<none>"])[0]
        key = (u.path.split("/api/")[1].split("/")[0] if "/api/" in u.path else u.path, ns)
        if key not in seen: seen.add(key); print("QUERY", u.path, "namespace=", ns)
    if page.locator("button:has-text('Skip tour')").count(): page.click("button:has-text('Skip tour')"); page.wait_for_timeout(1500)
    page.screenshot(path=f"{S}/observe-developer-{mode}.png")
    b.close()
