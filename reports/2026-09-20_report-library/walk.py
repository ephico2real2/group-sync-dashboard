#!/usr/bin/env python3
"""#229 on the deployed dashboard: the Library tab against the lab's real runs — the lead, every section
(the catalogue crossed with the three schedules), the cards' formats and expiry words, the run drawer opened
by position for a failed run, Copy link, the poll's repaint, 375 px. Logs in through oauth-proxy as
GSD_UI_USER with GSD_UI_PASSWORD; refuses a page with an uncaught error. Writes NN-*.png beside itself."""
import json, os, pathlib, sys
from playwright.sync_api import sync_playwright

BASE = os.environ.get("GSD_BASE", "https://group-sync-dashboard.apps-crc.testing")
OUT = pathlib.Path(__file__).resolve().parent
USER, PW = os.environ["GSD_UI_USER"], os.environ["GSD_UI_PASSWORD"]
FAILED = os.environ.get("GSD_FAILED_RUN", "20260919T020013.766694Z-d3eb")   # a failed nightly run on the lab

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

def shot(page, name, full=False):
    page.wait_for_timeout(400); page.screenshot(path=str(OUT / name), full_page=full); print("shot    :", name)

def main():
    with sync_playwright() as p:
        br = p.chromium.launch(); ctx = br.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 900})
        page = ctx.new_page(); errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
        login(page)
        page.goto(BASE + "/#page=library&cluster=crc-local", wait_until="networkidle")
        page.wait_for_selector("#library-lead", timeout=30_000); page.wait_for_timeout(800)
        lib = page.evaluate("() => ({ total: data.library.total, truncated: data.library.truncated, runs: data.library.runs.map(r => [r.id, r.report, r.generated_by, r.status, r.expires_at, r.retained_by]) })")
        print("api     :", json.dumps(lib))
        print("lead    :", " ".join(page.locator("#library-lead h2").inner_text().split()))
        heads = page.evaluate("() => [...document.querySelectorAll('.lib-sec')].map(s => [s.id, s.querySelector('h2').firstChild.textContent.trim(), [...s.classList].filter(c => c === 'paused' || c === 'compact').join(' ')])")
        print("sections:", heads)
        cards = page.evaluate("() => [...document.querySelectorAll('.run')].map(c => [c.id, c.querySelector('.when').textContent.trim(), [...c.querySelectorAll('.fmts .btn')].map(b => b.textContent), c.querySelector('.badge').textContent.trim(), c.querySelector('.expiry').textContent, (c.querySelector('.reason') || {}).textContent || ''])")
        print("cards   :", json.dumps(cards, ensure_ascii=False))
        shot(page, "01-library.png", full=True)
        page.goto(BASE + f"/#page=library&cluster=crc-local&run={FAILED}", wait_until="networkidle")
        page.wait_for_selector("#library-drawer", timeout=15_000); page.wait_for_timeout(500)
        print("drawer  :", " ".join(page.locator("#library-drawer").inner_text().split())[:600])
        print("focus   :", page.evaluate("() => document.activeElement.id"))
        page.click("#drawer-copy-link"); page.wait_for_function("() => document.getElementById('drawer-copy-link').textContent === 'Copied'")
        print("copied  :", page.evaluate("() => location.hash"))
        shot(page, "02-run-drawer.png")
        page.keyboard.press("Escape"); page.wait_for_function("() => !document.getElementById('library-drawer')")
        print("closed  :", page.evaluate("() => [location.hash, document.activeElement.id]"))
        page.set_viewport_size({"width": 375, "height": 740}); page.wait_for_timeout(600)
        print("375px   : no-x-overflow", page.evaluate("() => document.documentElement.scrollWidth <= innerWidth"))
        shot(page, "03-375.png")
        page.goto(BASE + f"/#page=library&cluster=crc-local&run={FAILED}", wait_until="networkidle")
        page.wait_for_selector("#library-drawer", timeout=15_000); page.wait_for_timeout(500)
        print("375 drawer: no-x-overflow", page.evaluate("() => document.getElementById('library-drawer').scrollWidth <= document.getElementById('library-drawer').clientWidth"))
        shot(page, "04-375-drawer.png")
        print("errors  :", errors); br.close(); sys.exit(1 if errors else 0)

if __name__ == "__main__":
    main()
