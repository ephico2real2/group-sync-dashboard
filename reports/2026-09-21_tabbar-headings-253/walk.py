#!/usr/bin/env python3
"""#253 on the deployed dashboard (Argo, rev 76d4e1e970): the tab bar on ONE row at every desktop
width, still WRAPPING at 375 without a sideways scroll, and the heading ladder at w700 with optical
tracking. Every printed line is a measurement the README quotes; the asserts fail the walk."""
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
  const cs=getComputedStyle(t[0]);
  return {tabs:t.length, rows:new Set(t.map(x=>Math.round(x.getBoundingClientRect().top))).size,
          need:Math.round(t.reduce((a,x)=>a+x.getBoundingClientRect().width,0)+gap*(t.length-1)),
          have:Math.round(bar.getBoundingClientRect().width), pad:cs.paddingLeft,
          scroll:[document.documentElement.scrollWidth, innerWidth]}; }"""
TYPE = """() => { const g=s=>{const e=document.querySelector(s); if(!e) return null;
  const c=getComputedStyle(e); return c.fontSize+' w'+c.fontWeight+' ls'+c.letterSpacing;};
  return {h1:g('h1'), h2:g('h2'), h3:g('h3')}; }"""

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(ignore_https_errors=True, color_scheme="light", viewport={"width":1440,"height":1000})
    p = ctx.new_page(); login(p)
    for page_id, shot in (("bindings","01-access-granted"), ("nsaudit","02-namespace-audit"), ("overview","03-overview")):
        p.goto(f"{BASE}/#page={page_id}", wait_until="networkidle"); p.wait_for_timeout(2200)
        bar, typ = p.evaluate(BAR), p.evaluate(TYPE)
        print(f"{page_id:<10} 1440 bar : {json.dumps(bar)}")
        print(f"{'':<10}      type: {json.dumps(typ)}")
        assert bar["rows"] == 1, f"{page_id}: the bar wrapped onto {bar['rows']} rows"
        assert bar["scroll"][0] <= bar["scroll"][1], f"{page_id}: scrolls sideways {bar['scroll']}"
        p.screenshot(path=str(OUT / f"{shot}-1440.png"))
    for w in (1280, 1180, 768, 375):
        p.set_viewport_size({"width": w, "height": 900})
        p.goto(f"{BASE}/#page=bindings", wait_until="networkidle"); p.wait_for_timeout(1800)
        bar = p.evaluate(BAR)
        print(f"bindings {w:>5} bar : {json.dumps(bar)}")
        assert bar["scroll"][0] <= bar["scroll"][1], f"{w}: scrolls sideways {bar['scroll']}"
        if w >= 1180: assert bar["rows"] == 1, f"{w}: wrapped onto {bar['rows']} rows"
        if w == 375:  assert bar["rows"] > 1, "375: the bar must wrap, not sit on one row"
        p.screenshot(path=str(OUT / f"04-access-granted-{w}.png"))
    print("WALK OK")
    ctx.close(); br.close()
