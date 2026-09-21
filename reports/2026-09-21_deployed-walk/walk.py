#!/usr/bin/env python3
"""The deployed head, walked with assertions (main @ 19ffb25b4a, Argo Synced/Healthy).

Covers what actually shipped today: the tab bar on one row at every desktop width and still WRAPPING
at phone width, the heading ladder at w700 with optical tracking, and the Namespace audit index
hiding platform namespaces with the count stated and the control restoring them. Every printed line
is a measurement; the asserts fail the walk rather than the reader."""
import json, os, pathlib
from playwright.sync_api import sync_playwright

BASE = os.environ.get("GSD_BASE", "https://group-sync-dashboard.apps-crc.testing")
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

BAR = """() => { const t=[...document.querySelectorAll('.tab')];
  const bar=document.querySelector('.tabs'); const gap=parseFloat(getComputedStyle(bar).gap)||0;
  return {tabs:t.length, rows:new Set(t.map(x=>Math.round(x.getBoundingClientRect().top))).size,
          need:Math.round(t.reduce((a,x)=>a+x.getBoundingClientRect().width,0)+gap*(t.length-1)),
          pad:getComputedStyle(t[0]).paddingLeft,
          scroll:[document.documentElement.scrollWidth, innerWidth]}; }"""
TYPE = """() => { const g=s=>{const e=document.querySelector(s); if(!e) return null;
  const c=getComputedStyle(e); return c.fontSize+' w'+c.fontWeight+' ls'+c.letterSpacing;};
  return {h1:g('h1'), h2:g('h2')}; }"""

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(ignore_https_errors=True, color_scheme="light", viewport={"width":1440,"height":1000})
    p = ctx.new_page(); login(p)
    print("head    :", p.evaluate("() => (document.body.innerText.match(/v[\\d.]+ · [0-9a-f]+/)||[])[0]"))

    for w in (1440, 1280, 1180, 768, 375):
        p.set_viewport_size({"width": w, "height": 900})
        p.goto(f"{BASE}/#page=bindings", wait_until="networkidle"); p.wait_for_timeout(1600)
        bar = p.evaluate(BAR)
        print(f"tabbar {w:>5}:", json.dumps(bar))
        assert bar["scroll"][0] <= bar["scroll"][1], f"{w}: scrolls sideways {bar['scroll']}"
        if w >= 1180: assert bar["rows"] == 1, f"{w}: wrapped onto {bar['rows']} rows"
        if w == 375:  assert bar["rows"] > 1, "375: the bar must wrap, not sit on one row"
        p.screenshot(path=str(OUT / f"01-tabbar-{w}.png"))

    p.set_viewport_size({"width": 1440, "height": 1000})
    p.goto(f"{BASE}/#page=nsaudit", wait_until="networkidle"); p.wait_for_timeout(2500)
    print("type    :", json.dumps(p.evaluate(TYPE)))
    # The control's OWN parent, not "any div containing the words": a loose selector matched a
    # container holding most of the page and printed it into the log, which makes the evidence
    # unreadable even when the assertion is sound.
    line = p.evaluate("""() => { const b=document.getElementById('ns-show-platform');
        return b ? b.parentElement.textContent.trim().replace(/\\s+/g,' ') : null; }""")
    rows = p.evaluate("() => document.querySelectorAll('tr[data-ns]').length")
    print("platform:", line)
    print("rows    :", rows)
    assert "67 platform namespaces hidden" in line, line
    assert "has a direct grant" in line, "the hidden-finding clause is missing"
    assert rows == 39, f"expected 39 non-platform rows, saw {rows}"
    p.screenshot(path=str(OUT / "02-nsaudit-filtered.png"), full_page=False)

    p.click("#ns-show-platform")
    p.wait_for_function("() => document.querySelectorAll('tr[data-ns]').length === 106")
    print("shown   :", p.evaluate("() => document.querySelectorAll('tr[data-ns]').length"), "rows after Show them")
    assert p.evaluate("() => document.activeElement && document.activeElement.id") == "ns-show-platform", "focus was lost"
    p.screenshot(path=str(OUT / "03-nsaudit-platform-shown.png"), full_page=False)
    print("WALK OK")
    ctx.close(); br.close()
