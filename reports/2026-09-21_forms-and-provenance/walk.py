#!/usr/bin/env python3
"""main @ 3ff11ea10d walked: #272's form fixes and #274's provenance wording, on the deployed page.

The form fixes were walked on their own branch; what has never been seen deployed is the provenance
wording — until now it was only asserted in tests. So this walk GENERATES a report on the lab and
reads the rendered rows back out of the artefact, which is what an auditor actually sees."""
import json, os, pathlib, re
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

FORM = """() => {
  const rows = [...document.querySelectorAll('#report-form .report-field')].map((f) => {
    const h = f.querySelector('.hint, .muted'); if (!h) return null;
    return {sw: h.scrollWidth, cw: h.clientWidth, size: getComputedStyle(h).fontSize};
  }).filter(Boolean);
  const stray = [...document.querySelectorAll('#report-form .report-field .muted, #report-form .report-field .linkish')]
    .map((e) => [e.textContent.replace(/\\s+/g,' ').trim().slice(0,30), getComputedStyle(e).fontSize])
    .filter(([, s]) => s !== '12px');
  return {clipped: rows.filter(r => r.sw > r.cw).length, n: rows.length, stray,
          page: [document.documentElement.scrollWidth, document.documentElement.clientWidth]};
}"""

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(ignore_https_errors=True, color_scheme="light", viewport={"width":1440,"height":1200})
    p = ctx.new_page(); login(p)
    head = p.evaluate("() => (document.body.innerText.match(/v[\\d.]+ · [0-9a-f]+/)||[])[0]")
    print("head    :", head)
    result = {"head": head}

    # ── #272: the forms, across every enabled report ────────────────────────────────────────────
    p.goto(f"{BASE}/#page=reports", wait_until="networkidle"); p.wait_for_selector("[data-report]", timeout=30_000)
    reports = p.evaluate("() => [...document.querySelectorAll('[data-report]')].map(r => r.dataset.report)")
    tot_clip = tot_stray = tot_hints = 0
    for r in reports:
        p.goto(f"{BASE}/#page=reports&report={r}", wait_until="networkidle")
        try: p.wait_for_selector("#report-form", timeout=15_000)
        except Exception: continue
        p.wait_for_timeout(900)
        m = p.evaluate(FORM)
        tot_clip += m["clipped"]; tot_stray += len(m["stray"]); tot_hints += m["n"]
        assert m["page"][0] <= m["page"][1], (r, m["page"])
    print(f"forms   : {len(reports)} reports, {tot_hints} hints — {tot_clip} clipped, {tot_stray} off-size")
    assert tot_clip == 0 and tot_stray == 0, (tot_clip, tot_stray)
    result["forms"] = {"reports": len(reports), "hints": tot_hints, "clipped": tot_clip, "stray": tot_stray}

    # ── #274: the provenance rows, read off a REAL generated report ─────────────────────────────
    p.goto(f"{BASE}/#page=reports&report=groups", wait_until="networkidle")
    p.wait_for_selector("#report-clusters", timeout=30_000)
    pdf = p.locator("#report-want-pdf")
    if pdf.count(): p.uncheck("#report-want-pdf")
    p.click("#report-generate")
    p.wait_for_function("() => view.reportRun && view.reportRun.status === 'done'", timeout=240_000)
    run_id = p.evaluate("() => view.reportRun.id")
    print("run     :", run_id)
    doc = p.evaluate("""async (id) => {
        const r = await reportFetch(`/api/runs/${encodeURIComponent(id)}/artifact?format=json`);
        return await r.json(); }""", run_id)
    prov = next(s for s in doc["sections"] if s["title"] == "Provenance and coverage")
    rows = {k: v for b in prov["blocks"] if b.get("items") for k, v in b["items"]}
    for label in ("Namespaces", "User objects", "Login capture"):
        print(f"  {label:14}: {rows[label]}")
        assert rows[label] not in ("ok", "off", "forbidden", "pending"), (label, rows[label])
    assert "attests absence" not in rows["Namespaces"], rows["Namespaces"]
    assert not rows["Namespaces"].startswith(("ok ", "off ", "forbidden ", "pending ")), rows["Namespaces"]
    claim = "a namespace with no grants is reported as having none"
    cannot = "‘no grants’ cannot be told from ‘never read’"
    assert (claim in rows["Namespaces"]) is doc["coverage"]["attests_absence"], rows["Namespaces"]
    assert (cannot in rows["Namespaces"]) is not doc["coverage"]["attests_absence"], rows["Namespaces"]
    print("  attests_absence (JSON, unchanged):", doc["coverage"]["attests_absence"])
    result["provenance"] = {k: rows[k] for k in ("Namespaces", "User objects", "Login capture")}
    result["attests_absence"] = doc["coverage"]["attests_absence"]
    p.screenshot(path=str(OUT / "01-groups-form.png"), full_page=True)

    # the provenance as the reader sees it, in the rendered HTML artefact
    p.evaluate("""async (id) => {
        const r = await reportFetch(`/api/runs/${encodeURIComponent(id)}/artifact?format=html`);
        const html = await r.text();
        document.open(); document.write(html); document.close(); }""", run_id)
    p.wait_for_timeout(1200)
    p.screenshot(path=str(OUT / "02-provenance-rendered.png"), full_page=False)
    (OUT / "walk.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))
    print("WALK OK")
    ctx.close(); br.close()
