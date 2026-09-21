#!/usr/bin/env python3
"""#143 phases 2–3 walked on the deployed dashboard: the namespace picker under Advanced, the totals
preview beside Generate (the refusal on an unscoped form, then the totals after a pick, with the
POST /report/api/preview body and answer captured), the reviewer prefill on access-certification,
and 375 px. Logs in through oauth-proxy as GSD_UI_USER with GSD_UI_PASSWORD; refuses a page with an
uncaught error. Writes NN-*.png beside itself and prints one line per measurement."""
import json, os, pathlib, sys
from playwright.sync_api import sync_playwright

BASE = os.environ.get("GSD_BASE", "https://group-sync-dashboard.apps-crc.testing")
OUT = pathlib.Path(__file__).resolve().parent
USER, PW = os.environ["GSD_UI_USER"], os.environ["GSD_UI_PASSWORD"]

def login(page):
    page.goto(BASE, wait_until="networkidle")
    b = page.locator("button:has-text('Log in with OpenShift')")
    if b.count(): b.first.click(); page.wait_for_load_state("networkidle")
    c = page.locator("a:has-text('developer')")
    if c.count(): c.first.click(); page.wait_for_load_state("networkidle")
    page.wait_for_selector("input[name='username']", timeout=20_000)
    page.fill("input[name='username']", USER); page.fill("input[name='password']", PW)
    page.click("button[type='submit'], input[type='submit']"); page.wait_for_load_state("networkidle")
    a = page.locator("input[name='approve']")
    if a.count(): a.first.click(); page.wait_for_load_state("networkidle")
    page.wait_for_selector("button.tab", timeout=30_000)

def shot(page, name):
    page.wait_for_timeout(400); page.screenshot(path=str(OUT / name), full_page=False); print("shot   :", name)

def main():
    with sync_playwright() as p:
        br = p.chromium.launch(); ctx = br.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 900})
        page = ctx.new_page(); errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
        previews = []
        page.on("response", lambda r: previews.append((r.status, r.request.post_data, r.text() if r.status != 429 else "")) if r.url.endswith("/report/api/preview") else None)
        login(page)
        page.goto(BASE + "/#page=reports&cluster=crc-local&report=namespace-access", wait_until="networkidle")
        page.wait_for_selector("#report-form.r-access")
        page.wait_for_function("() => document.getElementById('report-totals').textContent.startsWith('preview:')", timeout=20_000)
        print("totals  : unscoped →", page.locator("#report-totals").inner_text())
        page.click("details.report-advanced summary")
        page.wait_for_function("() => document.querySelectorAll('[data-lookup-opt=\"namespaces\"]').length > 0", timeout=20_000)
        listed = page.locator('[data-lookup-opt="namespaces"]').evaluate_all("es => es.map(e => e.dataset.value)")
        print("picker  :", len(listed), "namespaces discovered on crc-local, first", listed[:5])
        shot(page, "01-namespace-picker.png")
        page.fill("#report-lookup-namespace-access-namespaces", "group-sync"); page.wait_for_timeout(200)
        narrowed = page.evaluate("() => [...document.querySelectorAll('[data-lookup-opt=\"namespaces\"]')].filter(o => !o.hidden).map(o => o.dataset.value)")
        print("typeahead: 'group-sync' →", narrowed)
        pick = narrowed[0] if narrowed else listed[0]
        page.click(f'[data-lookup-opt="namespaces"][data-value="{pick}"]'); page.wait_for_selector(f'.rp-tag[data-name="{pick}"]')
        page.wait_for_function("() => /^\\d+ namespaces?/.test(document.getElementById('report-totals').textContent)", timeout=20_000)
        print("totals  :", pick, "→", page.locator("#report-totals").inner_text())
        last = previews[-1]; print("preview : POST", last[1], "→", last[0], last[2][:160])
        print("generate: enabled", page.locator("#report-generate").is_enabled())
        shot(page, "02-totals-beside-generate.png")
        page.goto(BASE + "/#page=reports&cluster=crc-local&report=access-certification", wait_until="networkidle")
        page.wait_for_selector("#report-form.r-compliance"); page.wait_for_timeout(600)
        print("reviewer: prefilled", repr(page.locator("#report-param-access-certification-reviewer").input_value()), "| signed in as", USER)
        page.wait_for_function("() => document.getElementById('report-totals').textContent !== ''", timeout=20_000)
        print("totals  : certification, unscoped →", page.locator("#report-totals").inner_text())
        shot(page, "03-reviewer-prefilled.png")
        page.set_viewport_size({"width": 375, "height": 740}); page.goto(BASE + "/#page=reports&cluster=crc-local&report=namespace-access", wait_until="networkidle")
        page.wait_for_selector("#report-form.r-access")
        if not page.locator("details.report-advanced").get_attribute("open") is not None:   # a hash navigation keeps the form's state, so Advanced may already be open
            page.click("details.report-advanced summary")
        page.wait_for_timeout(800)
        r = page.evaluate("() => [document.documentElement.scrollWidth <= innerWidth, document.querySelectorAll('[data-lookup-opt=\"namespaces\"]').length]")
        print("375px   : no-x-overflow, picker options", r)
        page.evaluate("() => { const el = document.getElementById('report-lookup-namespace-access-namespaces'); window.scrollTo(0, scrollY + el.getBoundingClientRect().top - 120); }"); page.wait_for_timeout(300)
        print("375px   : Advanced open", page.locator("details.report-advanced").get_attribute("open") is not None, "| picker input top", page.evaluate("() => Math.round(document.getElementById('report-lookup-namespace-access-namespaces').getBoundingClientRect().top)"))
        shot(page, "04-375-picker.png")
        print("errors  :", errors); br.close(); sys.exit(1 if errors else 0)

if __name__ == "__main__":
    main()
