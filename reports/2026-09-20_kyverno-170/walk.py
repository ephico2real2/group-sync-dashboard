#!/usr/bin/env python3
"""#170 on the deployed dashboard: the Kyverno tab against the lab's real reports — the state strip, the
deprecated-family and breaker notes, the policies table, the findings with the controlled-kind switch,
the history; the API payload's headline numbers beside the page's; 375 px. Logs in through oauth-proxy as
GSD_UI_USER with GSD_UI_PASSWORD; refuses a page with an uncaught error. Writes NN-*.png beside itself."""
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
        login(page)
        page.goto(BASE + "/#page=kyverno&cluster=crc-local", wait_until="networkidle")
        page.wait_for_function("() => data.kyverno && data.kyverno.present !== undefined", timeout=30_000); page.wait_for_timeout(800)
        d = page.evaluate("() => data.kyverno")
        print("api     :", json.dumps({k: d.get(k) for k in ("present", "api_group", "policy_kinds", "reports", "legacy_results", "other_results", "breaker_total", "breaker_drops", "results", "policies", "total")}))
        tiles = page.evaluate("() => [...document.querySelectorAll('#main .kpis .kpi')].map(k => [k.querySelector('.label').textContent, k.querySelector('.value').textContent, [...k.classList].filter(c => c.startsWith('flag-')).join('')])")
        print("tiles   :", tiles)
        print("legacy  :", " ".join(page.locator("#kyverno-legacy").inner_text().split())[:140] if page.locator("#kyverno-legacy").count() else "(no legacy note)")
        print("breaker :", " ".join(page.locator("#kyverno-breaker").inner_text().split())[:160])
        shot(page, "01-kyverno-state.png")
        pol = page.evaluate("() => [...document.querySelectorAll('#main section.card:nth-of-type(2) tbody tr')].map(tr => [...tr.cells].map(td => td.textContent.trim()))")
        print("policies:", pol)
        shot(page, "02-policies-and-findings.png")
        with page.expect_request(lambda r: "/kyverno?" in r.url and "controlled=true" in r.url):
            page.click("#kyverno-controlled")
        page.wait_for_timeout(1500)
        print("findings:", " ".join(page.locator("#main section.card:nth-of-type(3) h2").inner_text().split()), "| rows", page.locator("#main section.card:nth-of-type(3) tbody tr").count())
        print("history :", " ".join(page.locator("#main section.card:nth-of-type(4) h2").inner_text().split()))
        page.set_viewport_size({"width": 375, "height": 740}); page.wait_for_timeout(600)
        print("375px   : no-x-overflow", page.evaluate("() => document.documentElement.scrollWidth <= innerWidth"))
        shot(page, "03-375.png")
        print("errors  :", errors); br.close(); sys.exit(1 if errors else 0)

if __name__ == "__main__":
    main()
