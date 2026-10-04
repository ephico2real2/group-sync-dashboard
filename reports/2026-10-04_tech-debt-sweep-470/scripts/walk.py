#!/usr/bin/env python3
"""The Tech debt sweep's screens on the deployed dashboard (application 4.7.0), as `developer` under the walk's grant.

  - #587: the Reports description names CSV;
  - #577: the Generate label names the ticked formats plus JSON, after each change (nothing is generated);
  - #546: at 375 px the KPI Backups heading wraps its directory inside the card, with no sideways scroll;
  - #548: at 375 px every Database copies row shows its Delete button or its kept reason inside the viewport,
    and the card's note and form sit inside its padding. Nothing is clicked: no copy is deleted.

The UI password comes from the environment only (GSD_UI_PASSWORD) and is never printed. Exits non-zero on a page
error or a failed expectation."""
import json
import os
import pathlib
import re
import sys
import time

from playwright.sync_api import sync_playwright

BASE = os.environ.get("GSD_BASE", "https://group-sync-dashboard.apps-crc.testing")
USER, CLUSTER, REPORT = "developer", "dashboard", "groups"
SHOTS = pathlib.Path(__file__).resolve().parent.parent / "screenshots"
failures: list[str] = []
page_errors: list[str] = []


def say(tag: str, value) -> None:
    text = value if isinstance(value, str) else json.dumps(value)
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(re.sub(r"sha256~[A-Za-z0-9_-]+", "sha256~<redacted>", f"{stamp} {tag:60s}: {text}"), flush=True)


def expect(what: str, ok: bool, detail) -> None:
    say(f"{'PASS' if ok else 'FAIL'} {what}", detail)
    if not ok:
        failures.append(what)


def login(page) -> None:
    page.goto(BASE, wait_until="networkidle")
    b = page.locator("button:has-text('Log in with OpenShift')")
    if b.count(): b.first.click(); page.wait_for_load_state("networkidle")
    c = page.locator("a:has-text('developer')")           # CRC's htpasswd identity provider is named `developer`
    if c.count(): c.first.click(); page.wait_for_load_state("networkidle")
    page.wait_for_selector("input[name='username']", timeout=20_000)
    page.fill("input[name='username']", USER)
    page.fill("input[name='password']", os.environ["GSD_UI_PASSWORD"])
    page.click("button[type='submit'], input[type='submit']"); page.wait_for_load_state("networkidle")
    a = page.locator("input[name='approve']")
    if a.count(): a.first.click(); page.wait_for_load_state("networkidle")
    page.wait_for_function("() => typeof data !== 'undefined' && data.whoami && data.whoami.authenticated",
                           timeout=30_000)


def expected_label(page) -> str:
    """The label the ticked boxes call for, in box order, JSON always last."""
    names = [f.upper() for f in ("pdf", "html", "csv")
             if page.locator(f"#report-want-{f}").count() and page.is_checked(f"#report-want-{f}")]
    return " · ".join([*names, "JSON"])


def reports(page) -> None:
    page.click('button.tab:text-is("Reports")')
    page.wait_for_selector("#report-picker")
    note = page.locator("#report-picker .filterbar-note").inner_text()
    expect("#587 the Reports description names CSV", "CSV" in note, note)
    page.screenshot(path=str(SHOTS / "01-reports-description-1280.png"), full_page=False)

    page.goto(f"{BASE}/#page=reports&cluster={CLUSTER}&report={REPORT}", wait_until="networkidle")
    page.wait_for_selector("#report-generate span", timeout=30_000)
    label = page.locator("#report-generate span")
    boxes = [f for f in ("pdf", "html", "csv") if page.locator(f"#report-want-{f}").count()]
    say("format boxes on the form", boxes)
    seen = [(label.inner_text(), expected_label(page))]
    for f in boxes:                                      # flip each box, then flip it back
        (page.uncheck if page.is_checked(f"#report-want-{f}") else page.check)(f"#report-want-{f}")
        seen.append((label.inner_text(), expected_label(page)))
        if f == "csv":
            page.locator("#report-generate").scroll_into_view_if_needed()
            page.screenshot(path=str(SHOTS / "02-generate-label-after-a-change-1280.png"), full_page=False)
    for f in boxes:                                      # every box off: JSON alone
        page.uncheck(f"#report-want-{f}")
    seen.append((label.inner_text(), expected_label(page)))
    say("label, expected", seen)
    expect("#577 the label follows every change", all(a == b for a, b in seen), seen)
    expect("#577 every box off reads JSON", seen[-1][0] == "JSON", seen[-1])


def kpi_at_375(page) -> None:
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(f"{BASE}/#page=kpi", wait_until="networkidle")
    page.wait_for_selector("#hk-copies", timeout=30_000)
    page.wait_for_timeout(1000)

    heading = page.locator('section.kpi-page[data-card="backups"] h2').first
    if heading.count() and heading.locator(".asof").count():
        heading.scroll_into_view_if_needed()
        sizes = heading.evaluate("""(h) => {
            const r = h.getBoundingClientRect(), path = h.querySelector('.asof').getBoundingClientRect();
            return {text: h.innerText, scroll: h.scrollWidth, width: h.clientWidth, left: path.left, right: path.right,
                    innerLeft: r.left + parseFloat(getComputedStyle(h).paddingLeft),
                    innerRight: r.right - parseFloat(getComputedStyle(h).paddingRight)};
        }""")
        expect("#546 the Backups heading fits its card",
               sizes["scroll"] <= sizes["width"] and sizes["innerLeft"] <= sizes["left"] <= sizes["right"] <= sizes["innerRight"],
               sizes)
        page.locator('section.kpi-page[data-card="backups"]').screenshot(path=str(SHOTS / "03-kpi-backups-card-375.png"))
    else:
        expect("#546 the Backups heading is on the page", False, "no h2 with .asof naming Backups")

    card = page.locator("#hk-copies")
    card.scroll_into_view_if_needed()
    rows = card.locator("tbody tr").all()
    shown = {"rows": len(rows), "delete": card.locator("[data-hk-copy]").count(), "kept": card.locator(".hk-kept").count()}
    say("Database copies rows", shown)
    expect("#548 the card lists copies", len(rows) > 0, shown)
    for i, row in enumerate(rows):
        action = row.locator("[data-hk-copy], .hk-kept")
        bounds = action.first.evaluate("""(e) => {
            const r = e.getBoundingClientRect(), box = e.closest('.scroll-x');
            return {left: r.left, right: r.right, viewport: document.documentElement.clientWidth,
                    scroll: box.scrollWidth, width: box.clientWidth, offset: box.scrollLeft};
        }""") if action.count() == 1 else {"actions": action.count()}
        ok = (action.count() == 1 and action.first.is_visible()
              and 0 <= bounds["left"] <= bounds["right"] <= bounds["viewport"]
              and bounds["scroll"] <= bounds["width"] and bounds["offset"] == 0)
        expect(f"#548 row {i + 1}: its Delete or kept reason is in view", ok, bounds)
    padding = card.evaluate("""(c) => {
        const h = c.querySelector('h2'), r = h.getBoundingClientRect(), s = getComputedStyle(h);
        return {left: r.left + parseFloat(s.paddingLeft), right: r.right - parseFloat(s.paddingRight)};
    }""")
    for selector in (".hk-note", ".filterbar-note", ".hk-form"):
        box = card.locator(selector).first.bounding_box() if card.locator(selector).count() else None
        expect(f"#548 {selector} sits inside the card's padding",
               box is not None and box["x"] >= padding["left"] and box["x"] + box["width"] <= padding["right"],
               {"box": box, "padding": padding})
    card.screenshot(path=str(SHOTS / "04-kpi-database-copies-375.png"))
    overflow = page.evaluate("() => document.documentElement.scrollWidth > document.documentElement.clientWidth")
    expect("no sideways scroll on the KPI page at 375 px", not overflow, overflow)


def main() -> int:
    SHOTS.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1280, "height": 900}, ignore_https_errors=True)
        page = ctx.new_page()
        page.on("pageerror", lambda e: page_errors.append(str(e)))
        login(page)
        say("whoami", page.evaluate("() => ({ user: data.whoami.user, visibility: data.whoami.visibility })"))
        say("version", page.evaluate("() => (data.version || (data.whoami && data.whoami.version) || null)"))
        reports(page)
        kpi_at_375(page)
        expect("no page errors", not page_errors, page_errors)
        ctx.close(); browser.close()
    say("result", {"failures": failures})
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
