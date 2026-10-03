#!/usr/bin/env python3
"""SPEC_G3 §5 step 6: the Namespace audit tab on `dashboard`, the acknowledged disclosure closed and open.

Captured at 375, 768 and 1280 px, light and dark, as `developer` under the walk's screenshot grant (the spec names
`dana.lee`; that account's UI password is in no seed, so the wide tier is reached the way the earlier walks reach
it). The login is the one in reports/2026-10-03_platform-users-255/scripts/shots.py. The UI password comes from
the environment only (GSD_UI_PASSWORD) and is never printed. Exits non-zero on a page error, a missing disclosure,
or an open state without its two rows."""
import json
import os
import pathlib
import sys
import time

from playwright.sync_api import sync_playwright

BASE = os.environ.get("GSD_BASE", "https://group-sync-dashboard.apps-crc.testing")
SHOTS = pathlib.Path(__file__).resolve().parent.parent / "screenshots"
TOGGLE, ROWS = "[data-ns-ack]", "#ack-rows"


def say(tag: str, value) -> None:
    print(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {tag:44s}: {json.dumps(value)}", flush=True)


def login(page) -> None:
    page.goto(BASE, wait_until="networkidle")
    b = page.locator("button:has-text('Log in with OpenShift')")
    if b.count(): b.first.click(); page.wait_for_load_state("networkidle")
    c = page.locator("a:has-text('developer')")
    if c.count(): c.first.click(); page.wait_for_load_state("networkidle")
    page.wait_for_selector("input[name='username']", timeout=20_000)
    page.fill("input[name='username']", "developer")
    page.fill("input[name='password']", os.environ["GSD_UI_PASSWORD"])
    page.click("button[type='submit'], input[type='submit']"); page.wait_for_load_state("networkidle")
    a = page.locator("input[name='approve']")
    if a.count(): a.first.click(); page.wait_for_load_state("networkidle")
    page.wait_for_function("() => typeof data !== 'undefined' && data.whoami && data.whoami.authenticated", timeout=30_000)


def main() -> int:
    SHOTS.mkdir(exist_ok=True)
    failures, errors = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for scheme in ("light", "dark"):
            ctx = browser.new_context(ignore_https_errors=True, color_scheme=scheme, viewport={"width": 1280, "height": 900})
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            login(page)
            page.goto(f"{BASE}/#page=nsaudit&cluster=dashboard")
            page.wait_for_selector(TOGGLE, timeout=60_000)
            for width in (375, 768, 1280):
                page.set_viewport_size({"width": width, "height": 900})
                for state in ("closed", "open"):
                    expanded = page.locator(TOGGLE).get_attribute("aria-expanded") == "true"
                    if (state == "open") != expanded:
                        page.click(TOGGLE)
                        page.wait_for_timeout(300)
                    rows = page.locator(f"{ROWS} tbody tr").count() if state == "open" else 0
                    overflow = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
                    page.locator(TOGGLE).scroll_into_view_if_needed()
                    name = f"nsaudit-acknowledged-{state}-{width}-{scheme}.png"
                    page.screenshot(path=str(SHOTS / name))
                    say(name, {"aria-expanded": page.locator(TOGGLE).get_attribute("aria-expanded"), "rows": rows, "overflow px": overflow})
                    if state == "open" and rows != 2:
                        failures.append(name)
            ctx.close()
        browser.close()
    say("result", {"failures": failures, "page errors": errors})
    return 1 if failures or errors else 0


if __name__ == "__main__":
    sys.exit(main())
