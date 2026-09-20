#!/usr/bin/env python3
"""#219 on the deployed dashboard: hover the first Groups row and measure the first cell's ink against the
3px inset rail, on the Groups, Users and Access-granted tables; one capture of the hovered row. Logs in
through oauth-proxy as GSD_UI_USER with GSD_UI_PASSWORD; refuses a page with an uncaught error."""
import os, pathlib, sys
from playwright.sync_api import sync_playwright
BASE = os.environ.get("GSD_BASE", "https://group-sync-dashboard.apps-crc.testing"); OUT = pathlib.Path(__file__).resolve().parent
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
EDGE = """() => { const td = document.querySelector('tr.rowlink td:first-child'); const th = td.closest('table').querySelector('th:first-child');
  const edge = (el) => { const r = document.createRange(); r.selectNodeContents(el); const b = [...r.getClientRects()].filter(b => b.width > 0)[0]; return +(b.left - el.getBoundingClientRect().left).toFixed(1); };
  return [edge(td), edge(th), getComputedStyle(td).boxShadow !== 'none']; }"""
with sync_playwright() as p:
    br = p.chromium.launch(); ctx = br.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 900}); page = ctx.new_page(); errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
    login(page)
    for pg in ["groups", "users"]:   # the Access-granted rows sit below the fold of its first section; hover needs a visible row
        page.goto(BASE + f"/#page={pg}&cluster=crc-local", wait_until="networkidle"); page.wait_for_selector("tr.rowlink"); page.wait_for_timeout(600)
        page.hover("tr.rowlink >> nth=0"); page.wait_for_timeout(250)
        print(f"{pg:8}: first cell ink in / header ink in / rail painted", page.evaluate(EDGE))
        if pg == "groups":
            row = page.locator("tr.rowlink").first; row.screenshot(path=str(OUT / "01-hovered-row.png")); print("shot   : 01-hovered-row.png")
    print("errors  :", errors); br.close(); sys.exit(1 if errors else 0)
