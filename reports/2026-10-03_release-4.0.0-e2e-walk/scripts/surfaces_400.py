#!/usr/bin/env python3
"""The 4.0.0 surfaces the standard e2e walk does not open, captured VIEW-ONLY as `developer` under the walk's grant:
the Library's Clean up card and a run drawer's delete button (#542; nothing is pressed), the KPI page's Database
copies card (#542), and the Namespace audit tab's acknowledged grants, opened (#503), with its platform note (#255).
The login is the one in reports/2026-10-03_platform-users-255/scripts/shots.py. The UI password comes from the
environment only (GSD_UI_PASSWORD) and is never printed. Writes <out>/surfaces-400.json and <out>/screenshots/s400-*.png;
exits non-zero on a page error or a missing surface."""
import json
import os
import pathlib
import sys
import time

from playwright.sync_api import sync_playwright

BASE = os.environ.get("GSD_BASE", "https://group-sync-dashboard.apps-crc.testing")
OUT = pathlib.Path(sys.argv[1])
SHOTS = OUT / "screenshots"


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
    SHOTS.mkdir(parents=True, exist_ok=True)
    steps, errors = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(ignore_https_errors=True, viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        login(page)

        def shot(name, locator, what):
            ok = page.locator(locator).count() > 0
            if ok:
                page.locator(locator).first.scroll_into_view_if_needed()
                page.wait_for_timeout(300)
            page.screenshot(path=str(SHOTS / name))
            steps.append({"step": what, "ok": ok, "screenshot": f"screenshots/{name}", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})

        page.goto(f"{BASE}/#page=library&cluster=dashboard"); page.wait_for_selector("#lib-cleanup", timeout=60_000)
        shot("s400-01-library-cleanup-card.png", "#lib-cleanup", "#542 the Library's Clean up card")
        first = page.locator("article.run[data-run]").first      # a run card opens its drawer
        if first.count():
            first.click(); page.wait_for_selector("#drawer-delete", timeout=15_000)
        shot("s400-02-library-run-drawer.png", "#drawer-delete", "#542 a run drawer offers Delete this run (not pressed)")

        page.goto(f"{BASE}/#page=kpi"); page.wait_for_selector("#hk-copies", timeout=60_000)
        shot("s400-03-kpi-database-copies.png", "#hk-copies", "#542 the KPI page's Database copies card")

        page.goto(f"{BASE}/#page=nsaudit&cluster=dashboard"); page.wait_for_selector("[data-ns-ack]", timeout=60_000)
        if page.locator("[data-ns-ack]").get_attribute("aria-expanded") != "true":
            page.click("[data-ns-ack]"); page.wait_for_timeout(400)
        rows = page.locator("#ack-rows tbody tr").count()
        shot("s400-04-nsaudit-acknowledged-open.png", "[data-ns-ack]", f"#503 the acknowledged grants, opened ({rows} rows)")
        shot("s400-05-nsaudit-platform-note.png", "text=platform identities excluded", "#255 the platform identities note")
        browser.close()
    result = {"steps": steps, "page_errors": errors, "ack_rows": rows}
    (OUT / "surfaces-400.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({"ok": all(s["ok"] for s in steps) and not errors, "steps": [(s["step"], s["ok"]) for s in steps], "page_errors": errors}))
    return 0 if all(s["ok"] for s in steps) and not errors else 1


if __name__ == "__main__":
    sys.exit(main())
