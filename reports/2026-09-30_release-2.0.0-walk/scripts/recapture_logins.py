#!/usr/bin/env python3
"""Re-capture the Logins tab (screenshots/e2e-13-tab-logins.png) with e2e_masked.py's corrected mask, as `developer`
with the walk's grant, the way the e2e main pass captured it: e2e_capture.py's login, the same 1440 × 900 dark
context, the tab clicked and waited for as `walk_tabs` waits, and the same `Walk.shot` numbering (13). The first
capture's mask covered a sibling span, not the name (see TEXT_BOXES_JS in e2e_masked.py).

    GSD_UI_PASSWORD=… recapture_logins.py <out dir>     # writes <out dir>/13-tab-logins.png and a mask-log line"""
import os, pathlib, sys

import e2e_masked as m          # patches e2e_capture.Walk.shot; reads the fleet account from its Lease
from playwright.sync_api import sync_playwright

cap = m.cap
out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1, color_scheme="dark",
                              ignore_https_errors=True)
    page = ctx.new_page()
    w = cap.Walk(page, out)
    assert cap.login(w, "https://group-sync-dashboard.apps-crc.testing", "developer", os.environ["GSD_UI_PASSWORD"],
                     "developer"), "login failed"
    w.errors.clear()
    page.click('button.tab:text-is("Logins")')
    page.wait_for_selector('button.tab[aria-current="page"]:text-is("Logins")', timeout=15_000)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("h2", timeout=15_000)
    page.wait_for_timeout(700)
    problem = w.page_clean()
    w.n = 12
    name = w.shot("tab-logins")
    w.record("tab Logins (re-captured)", problem is None, problem or f"heading: {page.locator('h2').first.inner_text().strip()}", name)
    browser.close()
sys.exit(0 if all(s["ok"] for s in w.steps) else 1)
