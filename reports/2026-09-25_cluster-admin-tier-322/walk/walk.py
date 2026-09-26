#!/usr/bin/env python3
"""#322 on the deployed dashboard: the cluster-admin tier (`visibility.clusterAdminSar`, `update clusterrolebindings`).

Two personas log in through the oauth-proxy:
  - GSD_ADMIN_USER / GSD_ADMIN_PASSWORD: kubeadmin, a cluster-admin. Expected: KPI and Cluster Configurations
    tabs present, both routes 200, whoami.visibility.cluster_admin true.
  - GSD_READER_USER / GSD_READER_PASSWORD: a cluster-reader (passes `list clusterrolebindings`, fails `update`).
    Expected: both tabs ABSENT, both routes 403, the wide view still granted (tier `all`).
Passwords come from the environment only. Refuses a page with an uncaught error. Writes NN-*.png beside itself;
every printed line is a measurement the README quotes."""
import json, os, pathlib, sys
from playwright.sync_api import sync_playwright

BASE = os.environ.get("GSD_BASE", "https://group-sync-dashboard.apps-crc.testing")
OUT = pathlib.Path(__file__).resolve().parent
PERSONAS = [("admin", os.environ["GSD_ADMIN_USER"], os.environ["GSD_ADMIN_PASSWORD"]),
            ("reader", os.environ["GSD_READER_USER"], os.environ["GSD_READER_PASSWORD"])]


def login(page, user, pw):
    page.goto(BASE, wait_until="networkidle")
    b = page.locator("button:has-text('Log in with OpenShift')")
    if b.count(): b.first.click(); page.wait_for_load_state("networkidle")
    c = page.locator("a:has-text('developer')")           # CRC's htpasswd IdP carries kubeadmin and developer
    if c.count(): c.first.click(); page.wait_for_load_state("networkidle")
    page.wait_for_selector("input[name='username']", timeout=20_000)
    page.fill("input[name='username']", user); page.fill("input[name='password']", pw)
    page.click("button[type='submit'], input[type='submit']"); page.wait_for_load_state("networkidle")
    a = page.locator("input[name='approve']")
    if a.count(): a.first.click(); page.wait_for_load_state("networkidle")
    page.wait_for_selector("button.tab", timeout=30_000)


def shot(page, name, full=False):
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / name), full_page=full)
    print("shot     :", name)


def walk(browser, role, user, pw, n):
    ctx = browser.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 900})
    page = ctx.new_page(); errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
    login(page, user, pw)
    page.wait_for_function("() => typeof data !== 'undefined' && data.whoami && data.whoami.authenticated", timeout=30_000)
    tabs = page.evaluate("() => [...document.querySelectorAll('button.tab')].map(b => b.textContent.trim())")
    who = page.evaluate("() => ({ user: data.whoami.user, tier: data.whoami.tier,"
                        " cluster_admin: (data.whoami.visibility || {}).cluster_admin })")
    status = page.evaluate("""async () => { const s = {};
        for (const p of ['/api/kpi', '/api/clusterconfigs', '/api/whoami']) {
            s[p] = (await fetch(p, { credentials: 'same-origin' })).status; }
        return s; }""")
    print(f"{role:7s}  : whoami", json.dumps(who))
    print(f"{role:7s}  : tabs", json.dumps(tabs))
    print(f"{role:7s}  : has KPI tab", any(t.startswith("KPI") for t in tabs),
          "| has Cluster Configurations tab", any("Cluster Configurations" in t for t in tabs))
    print(f"{role:7s}  : status", json.dumps(status))
    shot(page, f"{n:02d}-{role}-home-1280.png")
    for page_id in ("kpi", "clusters"):
        page.goto(BASE + f"/#page={page_id}", wait_until="networkidle"); page.wait_for_timeout(1500)
        head = page.evaluate("() => { const m = document.querySelector('main') || document.body;"
                             " return m.innerText.replace(/\\s+/g, ' ').trim().slice(0, 160); }")
        print(f"{role:7s}  : #page={page_id} shows", json.dumps(head))
        n += 1
        shot(page, f"{n:02d}-{role}-{page_id}-1280.png")
    print(f"{role:7s}  : page errors", errors)
    ctx.close()
    return n + 1, errors


def main():
    errors = []
    with sync_playwright() as p:
        br = p.chromium.launch(); n = 1
        for role, user, pw in PERSONAS:
            n, errs = walk(br, role, user, pw, n); errors += errs
        br.close()
    print("errors   :", errors)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
