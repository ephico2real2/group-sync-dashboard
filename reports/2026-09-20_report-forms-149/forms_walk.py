#!/usr/bin/env python3
"""The report forms walked on the deployed dashboard (#149 R7): the shell, the lookups,
a chip, the POST, 375 px. Logs in through oauth-proxy as
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

def main():
    with sync_playwright() as p:
        br = p.chromium.launch(); ctx = br.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 900})
        page = ctx.new_page(); errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
        login(page)

    with sync_playwright() as p:
        br = p.chromium.launch(); ctx = br.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 900})
        page = ctx.new_page(); errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
        login(page)
        page.goto(BASE + "/#page=reports&cluster=crc-local&report=access-certification", wait_until="networkidle")
        page.wait_for_selector("#report-form.r-compliance"); page.wait_for_function("() => document.querySelectorAll('#report-subject .rp-opt').length > 0"); page.wait_for_timeout(600)
        users = page.locator('[data-lookup-opt="users"]').evaluate_all("es => es.map(e => e.dataset.value)")
        groups = page.locator('[data-lookup-opt="groups"]').evaluate_all("es => es.map(e => e.dataset.value)")
        mn = page.locator('[data-lookup-opt="group_mnemonic"]').evaluate_all("es => es.map(e => e.dataset.value)")
        print("lookups:", len(users), "users |", len(groups), "groups |", "mnemonics", mn)
        print("cluster field:", page.locator("#report-cluster").count(), "| required marks:", page.locator(".report-field .req").count(), "| switch:", page.locator('[data-switch="include_members"]').inner_text().strip())
        shot(page, "01-access-certification-shell.png")
        page.fill("#report-lookup-access-certification-groups", "alpha"); page.wait_for_timeout(200)
        narrowed = page.evaluate("() => [...document.querySelectorAll('[data-lookup-opt=\"groups\"]')].filter(o => !o.hidden).map(o => o.dataset.value)")
        print("typeahead:", "'alpha' →", narrowed[:4], "…" if len(narrowed) > 4 else "")
        page.click(f'[data-lookup-opt="groups"][data-value="{narrowed[0]}"]'); page.wait_for_selector(f'.rp-tag[data-name="{narrowed[0]}"]')
        if mn:
            page.click(f'[data-lookup-opt="group_mnemonic"][data-value="{mn[0]}"]'); page.wait_for_selector(f'.rp-tag[data-name="{mn[0]}"]')
        print("subject :", page.locator("#report-subject-count").inner_text(), "| chips:", page.locator(".rp-tag").evaluate_all("es => es.map(e => e.dataset.name)"))
        shot(page, "02-chips-added.png")
        page.fill("#report-param-access-certification-campaign", "Walk 2026-09-20"); page.locator("#report-param-access-certification-campaign").dispatch_event("change")
        page.fill("#report-param-access-certification-due", "2026-10-31"); page.locator("#report-param-access-certification-due").dispatch_event("change")
        page.fill("#report-param-access-certification-reviewer", "walk"); page.locator("#report-param-access-certification-reviewer").dispatch_event("change")
        with page.expect_request(lambda r: r.url.endswith("/api/runs") and r.method == "POST") as info:
            page.click("#report-generate")
        import json as _json
        body = _json.loads(info.value.post_data); print("POST    :", _json.dumps(body["params"]), "| formats:", body.get("formats"))
        page.wait_for_selector("#report-status:has-text('done'), #report-status:has-text('failed')", timeout=60_000); print("run     :", page.locator("#report-status").inner_text().replace("\n", " ")[:120])
        shot(page, "03-generated.png")
        page.goto(BASE + "/#page=reports&cluster=crc-local&report=namespace-access", wait_until="networkidle"); page.wait_for_selector("#report-form.r-access")
        page.click("details.report-advanced summary"); page.wait_for_timeout(300)
        print("group_by:", page.locator('[data-seg="group_by"]').evaluate_all("es => es.map(e => e.dataset.value + (e.getAttribute('aria-checked') === 'true' ? '*' : ''))"))
        shot(page, "04-namespace-access-advanced.png")
        page.set_viewport_size({"width": 375, "height": 740}); page.goto(BASE + "/#page=reports&cluster=crc-local&report=users", wait_until="networkidle")
        page.wait_for_selector("#report-form.r-identity"); page.wait_for_timeout(800)
        r = page.evaluate("() => { const f = document.getElementById('report-form').getBoundingClientRect(); return [Math.round(f.top), innerHeight, document.documentElement.scrollWidth <= innerWidth]; }")
        print("375px   :", "form top/viewport/no-x-overflow", r)
        shot(page, "05-375-users.png")
        print("errors  :", errors); br.close(); sys.exit(1 if errors else 0)

if __name__ == "__main__":
    main()
