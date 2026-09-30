#!/usr/bin/env python3
"""Offline proof of e2e_masked.py's text-box mask, with a made-up account name and no cluster login.

The page copies the Logins row that leaked — `<td class="mono">NAME <span class="muted">· FULL NAME</span></td>`, the
full name containing the account — below the fold, so a full-page capture is needed. It writes two captures into
<out dir>: `old.png` masked by `get_by_text` alone (the first commit's mask) and `01-new.png` through the patched
`Walk.shot`. OCR both afterwards; the old one must name the account and the new one must not.

    KUBECONFIG=… mask_fix_offline.py <out dir>      # oc is read once, by e2e_masked's import; nothing else"""
import json, pathlib, re, sys

import e2e_masked as m
from playwright.sync_api import sync_playwright

FAKE = "svc-walkfake-probe-account"
out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
m.FLEET, m.FLEET_RE, m.MASK_LOG = FAKE, re.compile(re.escape(FAKE), re.I), out / "mask-log.jsonl"
page_html = out / "page.html"
page_html.write_text(f"""<!doctype html><meta charset="utf-8">
<style>body{{font:14px sans-serif;background:#111;color:#eee}}.mono{{font-family:monospace}}.muted{{color:#999}}</style>
<div style="height:1200px"></div>
<table><tr><td class="mono">{FAKE} <span class="muted">· {FAKE}</span></td><td>2026-09-18</td></tr></table>""")
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1440, "height": 900})
    pg.goto(page_html.as_uri())
    pg.screenshot(path=str(out / "old.png"), full_page=True, mask=[pg.get_by_text(m.FLEET_RE)])
    shot = m.shot(m.cap.Walk(pg, out), "new")
    left = pg.locator("[data-walk-mask]").count()
    b.close()
print(json.dumps({"old": "old.png", "new": shot, "overlays_left_in_page": left,
                  "mask_log": json.loads(m.MASK_LOG.read_text().splitlines()[-1])}))
