#!/usr/bin/env python3
"""The Reporting status page walked on the deployed dashboard (#149 R5): the strip, the schedules,
the history's server-side filters, Back to Reports, 375 px. Logs in through oauth-proxy as
GSD_UI_USER with GSD_UI_PASSWORD; refuses a page with an uncaught error. Writes NN-*.png beside
itself and prints one line per measurement."""
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
    br = p.chromium.launch(); ctx = br.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 900})
    page = ctx.new_page(); errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
    login(page)
    page.click("#tab-reports"); page.wait_for_selector("#report-status-link")
    print("link   :", page.locator("#report-history-link").inner_text().strip().replace("\n", " "))
    page.click("#report-status-link"); page.wait_for_selector("#reporting-status .status-strip"); page.wait_for_timeout(600)
    print("hash   :", page.evaluate("location.hash"), "| back:", page.locator("#back").inner_text())
    for kv in page.locator("#reporting-status .kv").all():
        print("tile   :", kv.inner_text().replace("\n", " · "))
    shot(page, "01-status-strip.png")
    rows = page.locator("#reporting-schedules tbody tr").all()
    for r in rows:
        print("sched  :", " | ".join(c.inner_text().replace("\n", " ") for c in r.locator("td").all()))
    page.locator("#reporting-schedules").scroll_into_view_if_needed(); shot(page, "02-schedules.png")
    total = page.locator("#history-count").inner_text()
    page.select_option("#history-origin", "schedule"); page.wait_for_timeout(1200)
    sched_total = page.locator("#history-count").inner_text()
    page.select_option("#history-origin", ""); page.select_option("#history-status", "failed"); page.wait_for_timeout(1200)
    failed_total = page.locator("#history-count").inner_text()
    print("history:", "all", total, "| scheduled", sched_total, "| failed", failed_total, "| range", page.locator("#history-range").inner_text())
    page.select_option("#history-status", ""); page.wait_for_timeout(1200)
    page.locator("#reporting-history").scroll_into_view_if_needed(); shot(page, "03-history.png")
    page.click("#back"); page.wait_for_selector("#report-picker"); print("back   :", "to", page.evaluate("view.page"))
    page.set_viewport_size({"width": 375, "height": 740}); page.goto(BASE + "/#page=reporting&cluster=crc-local", wait_until="networkidle")
    page.wait_for_selector("#reporting-status .status-strip"); page.wait_for_timeout(600)
    print("375px  :", "no-x-overflow", page.evaluate("document.documentElement.scrollWidth <= innerWidth"),
          "| strip columns", page.evaluate("getComputedStyle(document.querySelector('.status-strip')).gridTemplateColumns.split(' ').length"))
    shot(page, "04-375.png")
    print("errors :", errors); br.close(); sys.exit(1 if errors else 0)
