#!/usr/bin/env python3
"""SPEC_F7 §5 step 3 (#593) on the deployed dashboard (5.1.0), as `developer` under the walk's grant: the Reports form
opens with only HTML ticked and the button reads "Generate HTML · JSON"; ticking PDF makes it "PDF · HTML · JSON".
Checked at 1280 and 375 px. Nothing is generated. The UI password comes from the environment only and is never printed."""
import json, os, pathlib, re, sys, time

from playwright.sync_api import sync_playwright

BASE = os.environ.get("GSD_BASE", "https://group-sync-dashboard.apps-crc.testing")
SHOTS = pathlib.Path(__file__).resolve().parent.parent / "screenshots"
failures: list[str] = []
errors: list[str] = []


def say(tag, value):
    text = value if isinstance(value, str) else json.dumps(value)
    print(re.sub(r"sha256~[A-Za-z0-9_-]+", "sha256~<redacted>", f"{time.strftime('%H:%M:%SZ', time.gmtime())} {tag:52s}: {text}"), flush=True)


def expect(what, ok, detail):
    say(f"{'PASS' if ok else 'FAIL'} {what}", detail)
    if not ok:
        failures.append(what)


def login(page):
    page.goto(BASE, wait_until="networkidle")
    b = page.locator("button:has-text('Log in with OpenShift')")
    if b.count(): b.first.click(); page.wait_for_load_state("networkidle")
    c = page.locator("a:has-text('developer')")             # CRC's htpasswd identity provider is named `developer`
    if c.count(): c.first.click(); page.wait_for_load_state("networkidle")
    page.wait_for_selector("input[name='username']", timeout=20_000)
    page.fill("input[name='username']", "developer")
    page.fill("input[name='password']", os.environ["GSD_UI_PASSWORD"])
    page.click("button[type='submit'], input[type='submit']"); page.wait_for_load_state("networkidle")
    a = page.locator("input[name='approve']")
    if a.count(): a.first.click(); page.wait_for_load_state("networkidle")
    page.wait_for_function("() => typeof data !== 'undefined' && data.whoami && data.whoami.authenticated", timeout=30_000)


def form(page, width):
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(f"{BASE}/#page=reports&cluster=dashboard&report=groups", wait_until="networkidle")
    page.wait_for_selector("#report-generate span", timeout=30_000)
    boxes = {f: page.is_checked(f"#report-want-{f}") for f in ("pdf", "html", "csv") if page.locator(f"#report-want-{f}").count()}
    label = page.locator("#report-generate span").inner_text()
    expect(f"{width} px: only HTML is ticked", boxes.get("html") is True and not boxes.get("pdf") and not boxes.get("csv"), boxes)
    expect(f"{width} px: the button reads Generate HTML · JSON", label == "HTML · JSON", label)
    page.locator("#report-generate").scroll_into_view_if_needed()
    page.screenshot(path=str(SHOTS / f"0{1 if width > 400 else 3}-form-opens-html-{width}.png"), full_page=False)
    page.check("#report-want-pdf")
    label = page.locator("#report-generate span").inner_text()
    expect(f"{width} px: ticking PDF reads PDF · HTML · JSON", label == "PDF · HTML · JSON", label)
    page.screenshot(path=str(SHOTS / f"0{2 if width > 400 else 4}-pdf-ticked-{width}.png"), full_page=False)
    overflow = page.evaluate("() => document.documentElement.scrollWidth > document.documentElement.clientWidth")
    expect(f"{width} px: no sideways scroll", not overflow, overflow)


def main():
    SHOTS.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for width in (1280, 375):           # a fresh session per width: the form keeps a reader's ticks (#575)
            ctx = browser.new_context(ignore_https_errors=True)
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            login(page)
            say("version", page.evaluate("() => data.version && {version: data.version.version, commit: data.version.commit}"))
            form(page, width)
            ctx.close()
        expect("no page errors", not errors, errors)
        browser.close()
    say("result", {"failures": failures})
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
