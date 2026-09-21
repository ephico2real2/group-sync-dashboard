#!/usr/bin/env python3
"""#230 S2 on the deployed dashboard — item 6 of #230's plan: the Cluster Configurations tab against the
lab's real rig (the in-cluster host, four Secret-sourced clusters across the three TLS modes and the
SA-token shape, one refusal finding, the retired rows), the Add-cluster form with its YAML twin, 375 px,
and the refusal card for a reader without the tier. Logs in through oauth-proxy as GSD_UI_USER with
GSD_UI_PASSWORD (kubeadmin) and, for the refusal, as GSD_DENIED_USER / GSD_DENIED_PASSWORD (a user
without `get secrets` in the release namespace). Refuses a page with an uncaught error. Writes NN-*.png
beside itself; every printed line is a measurement the README quotes."""
import json, os, pathlib, sys
from playwright.sync_api import sync_playwright

BASE = os.environ.get("GSD_BASE", "https://group-sync-dashboard.apps-crc.testing")
OUT = pathlib.Path(__file__).resolve().parent
USER, PW = os.environ["GSD_UI_USER"], os.environ["GSD_UI_PASSWORD"]
DENIED, DENIED_PW = os.environ.get("GSD_DENIED_USER"), os.environ.get("GSD_DENIED_PASSWORD")
CLEAN = lambda s: " ".join(s.split())

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

def shot(page, name, full=False, sel=None):
    page.wait_for_timeout(400)
    if sel: page.locator(sel).screenshot(path=str(OUT / name))
    else: page.screenshot(path=str(OUT / name), full_page=full)
    print("shot    :", name)

def walk_tab(page):
    page.goto(BASE + "/#page=clusters", wait_until="networkidle")
    page.wait_for_selector("#cc-head", timeout=30_000)
    page.wait_for_function("() => data.clusterconfigs && (data.clusterconfigs.clusters || []).length > 0", timeout=30_000)
    page.wait_for_timeout(800)
    print("tabs    :", page.evaluate("() => [...document.querySelectorAll('button.tab')].map(b => b.textContent.trim())"))
    print("whoami  :", json.dumps(page.evaluate("() => ({ user: data.whoami.user, clusterconfig: data.whoami.clusterconfig })")))
    api = page.evaluate("""() => { const d = data.clusterconfigs; return {
        secrets: d.secrets,
        clusters: d.clusters.map(c => ({ id: c.id, source: c.source, host: !!c.host, enabled: c.enabled, retired: !!c.retired,
            api_url: c.api_url, credential: c.credential, tls: c.tls, labels: c.labels, visibility: c.visibility,
            identity: c.identity, status: c.status, last_poll: c.last_poll, error: c.error })),
        findings: d.findings }; }""")
    print("api     :", json.dumps(api, ensure_ascii=False))
    print("lead    :", CLEAN(page.locator("#cc-head h2").inner_text()))
    print("head    :", json.dumps(page.evaluate("() => [...document.querySelectorAll('#cc-head .cc-kv')].map(r => [r.querySelector('.k').textContent.trim(), r.querySelector('.v').textContent.replace(/\\s+/g, ' ').trim()])"), ensure_ascii=False))
    rows = page.evaluate("""() => [...document.querySelectorAll('.cc-cluster')].map(c => {
        const kv = {}; c.querySelectorAll('.cc-kv').forEach(r => { kv[r.querySelector('.k').textContent.trim()] = r.querySelector('.v').textContent.replace(/\\s+/g, ' ').trim(); });
        return { id: c.dataset.ccCluster, title: c.querySelector('h2').textContent.replace(/\\s+/g, ' ').trim(),
                 chips: [...c.querySelectorAll('h2 .rp-chip')].map(x => x.textContent.trim()), kv,
                 foot: (c.querySelector('.cc-foot') || c.querySelector('.cc-acts') || { textContent: '' }).textContent.replace(/\\s+/g, ' ').trim() }; })""")
    for r in rows:
        print("row     :", json.dumps(r, ensure_ascii=False))
    print("findings:", json.dumps(page.evaluate("() => [...document.querySelectorAll('#cc-findings .cc-finding')].map(f => [...f.querySelectorAll('.cc-kv')].map(r => r.querySelector('.v').textContent.trim()))") or CLEAN(page.locator("#cc-findings").inner_text()), ensure_ascii=False))
    shot(page, "01-tab-1280.png", full=True)
    return rows

def walk_form(page):
    page.click("#cc-add-jump"); page.wait_for_timeout(300)
    page.fill("#cc-name", "walk-demo"); page.fill("#cc-server", "https://api.walk.example:6443")
    page.fill("#cc-token", "walk-token-not-a-real-credential")
    page.check("#cc-ca-trustedBundle")
    page.select_option("#cc-visibility", "self-only"); page.select_option("#cc-identity", "same-as-host")
    page.fill("#cc-label-key", "environment"); page.fill("#cc-label-val", "walk"); page.click("#cc-label-add")
    page.wait_for_function("() => document.querySelector('#cc-yaml').textContent.includes('gsd-cluster-walk-demo')", timeout=10_000)
    yaml = page.locator("#cc-yaml").inner_text()
    print("yaml    :", json.dumps(yaml))
    print("twin    :", json.dumps({
        "name_quoted": 'name: "gsd-cluster-walk-demo"' in yaml, "label_quoted": '"environment": "walk"' in yaml,
        "token_absent": "walk-token-not-a-real-credential" not in yaml, "redacted": '"bearerToken":"<redacted>"' in yaml,
        "insecure_false": '"insecure":false' in yaml, "enabled_string": 'enabled: "true"' in yaml}))
    print("writes  :", json.dumps({"create_button": page.locator("#cc-create").count(), "test_button": page.locator("#cc-test").count(),
                                   "note": CLEAN(page.locator("#cc-writes-off").inner_text()) if page.locator("#cc-writes-off").count() else None}))
    print("note    :", CLEAN(page.locator("#cc-add > .filterbar-note").first.inner_text()))
    shot(page, "02-add-form-1280.png", sel="#cc-add")

def walk_375(page):
    page.set_viewport_size({"width": 375, "height": 740}); page.wait_for_timeout(600)
    print("375px   : no-x-overflow", page.evaluate("() => document.documentElement.scrollWidth <= innerWidth"),
          "widest", page.evaluate("() => Math.max(...[...document.querySelectorAll('#cc-head, .cc-cluster, #cc-findings, #cc-add, #cc-yaml')].map(e => e.scrollWidth))"), "innerWidth", page.evaluate("() => innerWidth"))
    page.evaluate("() => window.scrollTo(0, 0)"); page.wait_for_timeout(200)
    shot(page, "03-tab-375.png", full=True)
    shot(page, "04-add-form-375.png", sel="#cc-add")

def walk_refusal(browser):
    if not (DENIED and DENIED_PW):
        print("refusal : skipped — GSD_DENIED_USER not set"); return []
    ctx = browser.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 900})
    page = ctx.new_page(); errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
    login(page, DENIED, DENIED_PW)
    print("denied  : tabs", page.evaluate("() => [...document.querySelectorAll('button.tab')].map(b => b.textContent.trim())"))
    page.goto(BASE + "/#page=clusters", wait_until="networkidle")
    page.wait_for_selector(".scope-refusal", timeout=30_000); page.wait_for_timeout(500)
    print("denied  : whoami", json.dumps(page.evaluate("() => ({ user: data.whoami.user, clusterconfig: data.whoami.clusterconfig, forbidden: data.clusterconfigs && data.clusterconfigs.forbidden })")))
    print("denied  : card", CLEAN(page.locator(".scope-refusal").inner_text()))
    print("denied  : api-requested", page.evaluate("() => performance.getEntriesByType('resource').some(e => e.name.includes('/api/clusterconfigs'))"))
    shot(page, "05-refusal-denied-1280.png")
    ctx.close(); return errors

def main():
    with sync_playwright() as p:
        br = p.chromium.launch(); ctx = br.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 900})
        page = ctx.new_page(); errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
        login(page, USER, PW)
        walk_tab(page); walk_form(page); walk_375(page)
        errors += walk_refusal(br)
        print("errors  :", errors); br.close(); sys.exit(1 if errors else 0)

if __name__ == "__main__":
    main()
