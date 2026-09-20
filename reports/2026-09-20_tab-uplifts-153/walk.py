#!/usr/bin/env python3
"""#153 walked on the deployed dashboard: the Groups KPI row against the Overview card's numbers and its
constancy under the state filter, Enter on a group name, the Users rails and provider chips, the review
rail, the Usage footnote, and every one of the four tabs at 375 px with no horizontal overflow. Logs in
through oauth-proxy as GSD_UI_USER with GSD_UI_PASSWORD; refuses a page with an uncaught error. Writes
NN-*.png beside itself and prints one line per measurement."""
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

def tiles(page, root=".kpis"):
    return page.evaluate(f"() => [...document.querySelectorAll('{root} .kpi')].map(k => [k.querySelector('.label').textContent.trim(), k.querySelector('.value').textContent.trim(), k.classList.contains('flag-warning') ? 'rail' : ''])")

def main():
    with sync_playwright() as p:
        br = p.chromium.launch(); ctx = br.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 900})
        page = ctx.new_page(); errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
        login(page)
        page.goto(BASE + "/#page=groups&cluster=crc-local", wait_until="networkidle"); page.wait_for_selector("#groups-kpis"); page.wait_for_timeout(600)
        print("groups  : KPIs", tiles(page, "#groups-kpis"), "| rows", page.locator("tr[data-group]").count())
        card = page.evaluate("() => { const c = (data.clusters || []).find(c => c.id === view.cluster); return [c.group_count, c.empty_groups, c.unattributed_groups]; }")
        print("groups  : /api/clusters says", card)
        shot(page, "01-groups-kpis.png")
        page.select_option("#f-state", "empty"); page.locator("#f-state").dispatch_event("change"); page.wait_for_timeout(1200)
        print("groups  : state=empty → KPIs", tiles(page, "#groups-kpis"), "| rows", page.locator("tr[data-group]").count())
        page.select_option("#f-state", "all"); page.locator("#f-state").dispatch_event("change"); page.wait_for_timeout(1200)
        first = page.locator("tr[data-group] button.drill").first; name = first.inner_text(); first.focus(); page.keyboard.press("Enter")
        page.wait_for_function(f"() => view.group === {name!r}"); page.wait_for_timeout(600)
        print("groups  : Enter on", name, "→ view.group", page.evaluate("() => view.group"))
        shot(page, "02-group-drill-by-keyboard.png")
        page.goto(BASE + "/#page=users&cluster=crc-local", wait_until="networkidle"); page.wait_for_selector("tr[data-user]"); page.wait_for_timeout(600)
        print("users   : KPIs", tiles(page))
        print("users   : provider chips on the first row", page.locator("tr[data-user]").first.locator("td:nth-child(3) .chip").all_inner_texts())
        shot(page, "03-users-rails-chips.png")
        page.goto(BASE + "/#page=bindings&cluster=crc-local", wait_until="networkidle"); page.wait_for_selector(".kpis .kpi"); page.wait_for_timeout(600)
        print("bindings: KPIs", tiles(page))
        shot(page, "04-bindings-review-rail.png")
        page.goto(BASE + "/#page=usage", wait_until="networkidle"); page.wait_for_selector(".kpis .kpi"); page.wait_for_timeout(600)
        leads = page.evaluate("() => [...document.querySelectorAll('#main .filterbar-note strong')].map(s => s.textContent).filter(t => ['Times', 'An interaction', 'Not logins.'].includes(t))")
        print("usage   : lead words", leads)
        shot(page, "05-usage-footnote.png")
        page.set_viewport_size({"width": 375, "height": 740})
        for pg in ["groups", "users", "bindings", "usage"]:
            page.goto(BASE + f"/#page={pg}&cluster=crc-local", wait_until="networkidle"); page.wait_for_timeout(1200)
            ok = page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
            print(f"375px   : {pg} no-x-overflow", ok)
            if pg in ("groups", "users"): shot(page, f"06-375-{pg}.png")
        print("errors  :", errors); br.close(); sys.exit(1 if errors else 0)

if __name__ == "__main__":
    main()
