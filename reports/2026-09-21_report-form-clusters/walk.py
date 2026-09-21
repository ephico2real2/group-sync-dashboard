#!/usr/bin/env python3
"""#267/#269 walked on the deployed head: the report form names its cluster, and runs on several.

The lab has five configured clusters, so this walk is the thing the hermetic tests cannot be — the
control against a real estate rather than a two-cluster fixture. It also drives two of the three defects
OB1-lite found in the review of #269 (the fleet-path note and the per-form dismiss) on the deployed
page, because the headless harness is not the deployed page. The third (V2, a poll failure worded as
a refusal) needs an aborted request and is left to the browser test, which can route-abort.

Every printed line is a measurement and every assert fails the walk rather than the reader."""
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

CHIPS = """() => [...document.querySelectorAll('[data-cluster-pick]')].map(b => ({
    id: b.dataset.clusterPick, on: b.getAttribute('aria-checked') === 'true',
    primary: b.classList.contains('primary'), disabled: b.getAttribute('aria-disabled') === 'true'}))"""
NOTE = """() => { const n = document.getElementById('report-cluster-note');
    return n ? n.innerText.replace(/\\s+/g, ' ').trim() : null; }"""

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(ignore_https_errors=True, color_scheme="light", viewport={"width": 1440, "height": 1100})
    p = ctx.new_page(); login(p)
    print("head    :", p.evaluate("() => (document.body.innerText.match(/v[\\d.]+ · [0-9a-f]+/)||[])[0]"))

    clusters = p.evaluate("() => (data.clusters || []).map(c => c.id)")
    print("clusters:", clusters)
    assert len(clusters) == 5, f"the reference estate is five clusters, saw {clusters}"

    # ── 1. the control, on a real estate ────────────────────────────────────────────────────────
    p.goto(f"{BASE}/#page=reports&report=groups", wait_until="networkidle")
    p.wait_for_selector("#report-clusters", timeout=30_000); p.wait_for_timeout(1200)
    chips = p.evaluate(CHIPS)
    nav = p.evaluate("() => view.cluster")
    count = p.locator("#report-cluster-count").inner_text()
    print("chips   :", json.dumps(chips))
    print("nav     :", nav, "| count:", count)
    assert [c["id"] for c in chips] == clusters, "the chips are the nav's list, in the nav's order"
    assert [c["id"] for c in chips if c["primary"]] == [nav], "the nav's cluster is the primary"
    assert [c["id"] for c in chips if c["on"]] == [nav], "the control defaults to the nav's cluster alone"
    assert count == "1 of 5 clusters", count
    assert [c["id"] for c in chips if c["disabled"]] == [nav], "the last checked chip cannot be unchecked"
    p.screenshot(path=str(OUT / "01-control-default.png"), full_page=False)

    # ── 2. all five, then back to one ───────────────────────────────────────────────────────────
    p.click("#report-clusters-all")
    p.wait_for_function("() => document.getElementById('report-cluster-count').textContent === '5 of 5 clusters'")
    chips = p.evaluate(CHIPS)
    print("all     :", p.locator("#report-cluster-count").inner_text(),
          "| disabled:", [c["id"] for c in chips if c["disabled"]])
    assert all(c["on"] for c in chips), "all five are checked"
    assert not any(c["disabled"] for c in chips), "with five checked, none is the last"
    p.screenshot(path=str(OUT / "02-all-five.png"), full_page=False)

    # ── 3. the fan-out: one run per cluster, each its own document ──────────────────────────────
    #    MEASURED 2026-09-21: all five seal, shared-rnd included — it has a snapshot on this lab, so
    #    the partial-failure path is NOT exercised here and remains covered only by the API test
    #    (test_one_cluster_the_snapshot_lacks_fails_its_own_run_and_no_other). What this proves on a
    #    real estate is the fan-out itself: five runs, five distinct seals, one action.
    pdf = p.locator("#report-want-pdf")
    if pdf.count(): p.uncheck("#report-want-pdf")
    p.click("#report-generate")
    p.wait_for_selector("#report-batch", timeout=30_000)
    p.wait_for_function("() => view.reportBatch && view.reportBatch.runs.length === 5 && "
                        "view.reportBatch.runs.every(r => r.status === 'done' || r.status === 'failed')",
                        timeout=240_000)
    runs = p.evaluate("() => view.reportBatch.runs.map(r => ({cluster: r.cluster, status: r.status, "
                      "sha: r.sha256 && r.sha256.slice(0, 12), error: r.error}))")
    head = p.locator("#report-batch .rp-batch-head").inner_text().strip()
    print("batch   :", head)
    for r in runs: print("  run   :", json.dumps(r))
    assert [r["cluster"] for r in runs] == clusters, "one run per cluster, in the order asked"
    assert "the request was refused" not in head, head
    done = [r for r in runs if r["status"] == "done"]
    assert len(done) == len(clusters), f"every configured cluster sealed on 2026-09-21; a change here is the finding: {runs}"
    shas = [r["sha"] for r in done]
    assert len(set(shas)) == len(shas), f"each artefact is its own gathering: {shas}"
    for r in runs:
        if r["status"] == "failed": assert r["error"], f"a failed run states its reason: {r}"
    p.screenshot(path=str(OUT / "03-fan-out.png"), full_page=True)

    # ── 4. the fleet-path note (#269 V1) ────────────────────────────────────────────────────────
    #    Overview leaves view.cluster null (#172); the boot cycle then stamps the first cluster
    #    OUTSIDE navigate(), so the note the reader comes back to is the one recorded with to:null.
    other = next(c for c in clusters if c != nav)
    p.goto(f"{BASE}/#page=reports&report=access-matrix", wait_until="networkidle")
    p.wait_for_selector("#report-form", timeout=30_000)
    p.wait_for_function("() => document.querySelectorAll('[data-lookup-opt=\"users\"]').length > 0", timeout=60_000)
    picked = p.evaluate("() => document.querySelector('[data-lookup-opt=\"users\"]').dataset.value")
    p.click('[data-lookup-opt="users"] >> nth=0')
    p.wait_for_selector(".rp-tag", timeout=15_000)
    print("picked  :", picked, "on", p.evaluate("() => view.cluster"))
    p.click("#tab-overview"); p.wait_for_function("() => view.cluster === null", timeout=30_000)
    p.click("#tab-reports"); p.click("[data-report='access-matrix']")
    p.wait_for_function("() => view.cluster && !!document.getElementById('report-cluster-note')", timeout=60_000)
    note = p.evaluate(NOTE)
    print("note    :", note)
    assert "to the fleet view" in note, f"the fleet is named for what it is: {note}"
    assert " to — " not in note and "are 's" not in note, f"the pre-#269 garbled sentence is back: {note}"
    assert f"the lookups now offered are {p.evaluate('() => view.cluster')}'s" in note, note
    assert p.locator(".rp-tag").count() == 0, "the lookup really went, whatever the note says"
    p.screenshot(path=str(OUT / "04-fleet-note.png"), full_page=False)

    # ── 5. dismiss is this form's (#269 V3) ─────────────────────────────────────────────────────
    p.click("#report-cluster-note-x")
    p.wait_for_function("() => !document.getElementById('report-cluster-note')")
    print("dismiss : the note is gone on access-matrix")
    p.screenshot(path=str(OUT / "05-dismissed.png"), full_page=False)
    print("WALK OK")
    ctx.close(); br.close()
