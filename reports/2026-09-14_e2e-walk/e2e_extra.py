#!/usr/bin/env python3
"""Second pass: the parts of the walk that need a different context or a file, not a tab.

- the cluster selector switched to the second configured cluster (D2's per-cluster row)
- the light theme, one page, to show both shipped themes render
- the downloaded HTML reports opened in the browser and captured full-page
- the first page of every downloaded PDF rendered to PNG (macOS sips)
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from e2e_capture import Walk, login, now  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

BASE = "https://group-sync-dashboard.apps-crc.testing"
RUN = pathlib.Path(sys.argv[1])
OUT = RUN / "extra"
OUT.mkdir(exist_ok=True)
password = os.environ["GSD_UI_PASSWORD"]

with sync_playwright() as p:
    browser = p.chromium.launch()
    # 1. Dark theme: the second cluster and the whoami pill.
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="dark", ignore_https_errors=True)
    page = ctx.new_page()
    w = Walk(page, OUT)
    assert login(w, BASE, "kubeadmin", password, "developer")
    ids = [o.strip() for o in page.locator("select#f-cluster option").all_inner_texts()]
    w.record("cluster selector options", True, ", ".join(ids) or "(selector not found)")
    other = [i for i in ids if i not in ("crc-local", "all", "All clusters")]
    if other:
        sel = page.locator("select#f-cluster")
        sel.select_option(label=other[0])
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(900)
        shot = w.shot(f"overview-cluster-{other[0]}")
        w.record(f"switch cluster to {other[0]}", w.page_clean() is None,
                 f"heading: {page.locator('h2').first.inner_text().strip()}; url {page.url}", shot)
        page.click('button.tab:text-is("Reports")')
        page.wait_for_selector('button.tab[aria-current="page"]:text-is("Reports")', timeout=15_000)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)
        form = page.locator("#report-cluster")
        text = page.locator("main, body").first.inner_text()
        val = form.input_value() if form.count() else None
        shot = w.shot(f"reports-cluster-{other[0]}")
        w.record(f"Reports tab on {other[0]}", True,
                 (f"the report form's read-only cluster field says {val}" if val else
                  "no report form; the card says: " + " ".join(text.split())[:300]), shot)
    pill = page.locator("#scope-pill")
    w.record("scope pill", True, pill.inner_text().strip() if pill.count() else "(no pill element found)")
    ctx.close()

    # 2. Light theme, Overview only.
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="light", ignore_https_errors=True)
    page = ctx.new_page()
    w2 = Walk(page, OUT); w2.n = w.n
    assert login(w2, BASE, "kubeadmin", password, "developer")
    shot = w2.shot("overview-light-theme", full=False)
    w2.record("light theme Overview", w2.page_clean() is None, "prefers-color-scheme: light", shot)
    ctx.close()

    # 3. The HTML reports, opened from the downloaded files.
    ctx = browser.new_context(viewport={"width": 1200, "height": 900}, color_scheme="light")
    page = ctx.new_page()
    w3 = Walk(page, OUT); w3.n = w2.n
    for html in sorted((RUN / "reports").glob("*.html")):
        page.goto(html.as_uri(), wait_until="load")
        page.wait_for_timeout(300)
        title = page.title()
        name = html.name.split("_")[2]
        shot = w3.shot(f"html-report-{name}")
        w3.record(f"HTML report {name} opens", not w3.errors, f"title: {title}; {html.stat().st_size} bytes", shot)
        w3.errors.clear()
    ctx.close()
    browser.close()

# 4. First page of every PDF → PNG via sips (macOS).
pdf_pngs = []
for pdf in sorted((RUN / "reports").glob("*.pdf")):
    name = pdf.name.split("_")[2]
    png = OUT / f"pdf-page1-{name}.png"
    r = subprocess.run(["sips", "-s", "format", "png", str(pdf), "--out", str(png)], capture_output=True, text=True)
    ok = r.returncode == 0 and png.exists()
    pdf_pngs.append({"report": name, "ok": ok, "png": png.name, "err": r.stderr.strip()[:200]})
    print(f"  [{'ok ' if ok else 'FAIL'}] pdf page 1 → {png.name}")

steps = w.steps + w2.steps + w3.steps
(OUT / "results_extra.json").write_text(json.dumps({"finished": now(), "steps": steps, "pdf_page1": pdf_pngs}, indent=2, default=str))
print(f"{sum(s['ok'] for s in steps)} / {len(steps)} extra steps ok; {sum(x['ok'] for x in pdf_pngs)} / {len(pdf_pngs)} PDFs rendered")
