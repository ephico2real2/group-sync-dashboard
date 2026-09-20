#!/usr/bin/env python3
"""The Reports page walked on the deployed dashboard (#173): the catalogue, a click's landing,
the back control, a deep link, Back/Forward, and 375 px. Logs in through oauth-proxy as
GSD_UI_USER (kubeadmin via the `developer` provider on CRC) with GSD_UI_PASSWORD; refuses to
capture a page with an uncaught error. Writes NN-*.png beside itself and prints one line per
measurement."""
import os, pathlib, sys
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

with sync_playwright() as p:
    br = p.chromium.launch(); ctx = br.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 800})
    page = ctx.new_page(); errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
    login(page)
    page.click("#tab-reports"); page.wait_for_selector("#report-picker table.report-table")
    print("rows   :", page.locator("tr.report-pick").count(), "| count chip:", page.locator("#report-picker .rp-count").inner_text().strip(),
          "| form open on arrival:", page.locator("#report-form").count() == 1)
    print("keys   :", page.locator(".rp-key").evaluate_all("es => es.map(e => e.textContent)"))
    print("weight :", page.locator("#report-pick-namespace-access .rp-title").evaluate("e => getComputedStyle(e).fontWeight"))
    shot(page, "01-catalogue.png")
    page.click("#report-pick-access-certification")
    page.wait_for_function("() => view.report === 'access-certification' && document.getElementById('report-form')")
    page.wait_for_timeout(700)
    r = page.evaluate("() => { const f = document.getElementById('report-form').getBoundingClientRect(); return [Math.round(f.top), Math.round(f.bottom), innerHeight]; }")
    print("landed :", "form top/bottom/viewport", r, "| hash:", page.evaluate("location.hash"), "| back:", page.locator("#report-back").inner_text())
    shot(page, "02-click-lands-in-view.png")
    page.click("#report-pick-groups"); page.wait_for_selector("#report-form.r-identity"); page.wait_for_timeout(700)
    print("second :", "back control:", page.locator("#report-back").inner_text(), "| hash:", page.evaluate("location.hash"))
    shot(page, "03-back-control-names-previous.png")
    page.click("#report-back"); page.wait_for_selector("#report-form.r-compliance"); page.wait_for_timeout(400)
    print("back   :", "returned to", page.evaluate("view.report"))
    page.go_back(); page.wait_for_function("() => view.report === null"); page.wait_for_timeout(400)
    print("back2  :", "form present:", page.locator("#report-form").count(), "| hash:", page.evaluate("location.hash"))
    page.go_forward(); page.wait_for_function("() => view.report === 'access-certification'")
    print("forward:", page.evaluate("view.report"))
    page.goto(BASE + "/#page=reports&cluster=crc-local&report=namespace-access", wait_until="networkidle")
    page.wait_for_selector("#report-form.r-access"); page.wait_for_timeout(700)
    print("deep   :", "back control:", page.locator("#report-back").inner_text(), "| form top:", page.evaluate("Math.round(document.getElementById('report-form').getBoundingClientRect().top)"))
    shot(page, "04-deep-link.png")
    page.set_viewport_size({"width": 375, "height": 740}); page.wait_for_timeout(600)
    page.click("#report-back"); page.wait_for_function("() => view.report === null")
    page.click("#report-pick-compliance-snapshot"); page.wait_for_function("() => view.report === 'compliance-snapshot'"); page.wait_for_timeout(800)
    r = page.evaluate("() => { const f = document.getElementById('report-form').getBoundingClientRect(); return [Math.round(f.top), innerHeight, document.documentElement.scrollWidth <= innerWidth, getComputedStyle(document.querySelector('.report-table-wrap')).overflowX]; }")
    print("375px  :", "form top/viewport/no-x-overflow/wrap", r)
    shot(page, "05-375-form.png")
    page.evaluate("window.scrollTo(0,0)"); page.wait_for_timeout(400); shot(page, "06-375-catalogue.png")
    print("errors :", errors)
    br.close()
    sys.exit(1 if errors else 0)
