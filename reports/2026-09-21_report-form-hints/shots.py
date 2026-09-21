#!/usr/bin/env python3
"""Capture the report forms on the deployed page, for the before/after of #272.

Run once against the build that carries the defects and once against the fix; SHOT_TAG names which.
namespace-access is the form that shows every defect at once: the worst truncation (1548px of text in
a 264px column) and all four stray 14px elements in its selector block."""
import json, os, pathlib
from playwright.sync_api import sync_playwright

BASE = os.environ.get("GSD_BASE", "https://group-sync-dashboard.apps-crc.testing")
TAG = os.environ.get("SHOT_TAG", "before")
OUT = pathlib.Path(__file__).resolve().parent
USER, PW = os.environ["GSD_UI_USER"], os.environ["GSD_UI_PASSWORD"]

def login(page):
    page.goto(BASE, wait_until="networkidle")
    for sel in ("button:has-text('Log in with OpenShift')", "a:has-text('developer')"):
        l = page.locator(sel)
        if l.count(): l.first.click(); page.wait_for_load_state("networkidle")
    page.wait_for_selector("input[name='username']", timeout=20_000)
    page.fill("input[name='username']", USER); page.fill("input[name='password']", PW)
    page.click("button[type='submit'], input[type='submit']"); page.wait_for_load_state("networkidle")
    a = page.locator("input[name='approve']")
    if a.count(): a.first.click(); page.wait_for_load_state("networkidle")
    page.wait_for_selector("button.tab", timeout=30_000)

MEASURE = """() => {
  const rows = [...document.querySelectorAll('#report-form .report-field')].map((f) => {
    const h = f.querySelector('.hint, .muted'), l = f.querySelector('label');
    if (!h) return null;
    return {text: h.textContent.replace(/\\s+/g,' ').trim().slice(0,46), sw: h.scrollWidth, cw: h.clientWidth,
            hint: getComputedStyle(h).fontSize, label: l ? getComputedStyle(l).fontSize : null};
  }).filter(Boolean);
  const stray = [...document.querySelectorAll('#report-form .report-field .muted, #report-form .report-field .linkish')]
    .map((e) => [e.textContent.replace(/\\s+/g,' ').trim().slice(0,34), getComputedStyle(e).fontSize])
    .filter(([, s]) => s !== '12px');
  return {rows, stray, page: [document.documentElement.scrollWidth, document.documentElement.clientWidth]};
}"""

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(ignore_https_errors=True, color_scheme="light", viewport={"width":1440,"height":1200})
    p = ctx.new_page(); login(p)
    print(TAG, "head:", p.evaluate("() => (document.body.innerText.match(/v[\\d.]+ · [0-9a-f]+/)||[])[0]"))
    out = {}
    for report in ("namespace-access", "groups"):
        p.goto(f"{BASE}/#page=reports&report={report}", wait_until="networkidle")
        p.wait_for_selector("#report-form", timeout=30_000); p.wait_for_timeout(1500)
        m = p.evaluate(MEASURE); out[report] = m
        clipped = [r for r in m["rows"] if r["sw"] > r["cw"]]
        print(f"  {report}: {len(clipped)} clipped, {len(m['stray'])} stray-size, page {m['page']}")
        for r in clipped: print(f"     CLIP {r['sw']}>{r['cw']} hint={r['hint']} label={r['label']}  {r['text']}")
        for t, s in m["stray"]: print(f"     SIZE {s}  {t}")
        p.screenshot(path=str(OUT / f"{TAG}-{report}-1440.png"), full_page=True)
    # the groups lookup open, to show the member counts
    p.goto(f"{BASE}/#page=reports&report=access-matrix", wait_until="networkidle")
    p.wait_for_selector("#report-form", timeout=30_000)
    p.wait_for_function("() => document.querySelectorAll('[data-lookup-opt=\"groups\"]').length > 0", timeout=60_000)
    opts = p.evaluate("() => [...document.querySelectorAll('[data-lookup-opt=\"groups\"]')].slice(0,4).map(o => o.textContent.replace(/\\s+/g,' ').trim())")
    print("  group options:", json.dumps(opts))
    out["group_options"] = opts
    p.screenshot(path=str(OUT / f"{TAG}-groups-lookup-1440.png"), full_page=False)
    p.set_viewport_size({"width": 375, "height": 900})
    p.goto(f"{BASE}/#page=reports&report=namespace-access", wait_until="networkidle")
    p.wait_for_selector("#report-form", timeout=30_000); p.wait_for_timeout(1500)
    m375 = p.evaluate(MEASURE); out["namespace-access@375"] = m375
    print(f"  namespace-access@375: {len([r for r in m375['rows'] if r['sw']>r['cw']])} clipped, page {m375['page']}")
    p.screenshot(path=str(OUT / f"{TAG}-namespace-access-375.png"), full_page=True)
    (OUT / f"{TAG}.json").write_text(json.dumps(out, indent=1))
    ctx.close(); br.close()
