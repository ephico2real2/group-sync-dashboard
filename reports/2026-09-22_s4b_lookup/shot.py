#!/usr/bin/env python3
"""SPEC_S4b §5, the picture: the Cluster Configurations tab on the deployed head, logged in through the
proxy as the htpasswd developer, showing the retrieved cluster's card (credential bearerToken, source
its written Secret) and the Findings card. Same login as reports/2026-09-21_forms-and-provenance/walk.py."""
import json, os, pathlib, sys
from playwright.sync_api import sync_playwright

BASE = os.environ.get("GSD_BASE", "https://group-sync-dashboard.apps-crc.testing")
OUT = pathlib.Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
USER, PW = os.environ["GSD_UI_USER"], os.environ["GSD_UI_PASSWORD"]
IDP = os.environ.get("GSD_UI_IDP", "developer")   # the login page's identity-provider link: kube:admin for kubeadmin
CLUSTERS = sys.argv[2:] or ["rnd-lookup"]


def login(page):
    page.goto(BASE, wait_until="networkidle")
    for sel in ("button:has-text('Log in with OpenShift')", f"a:has-text('{IDP}')"):
        l = page.locator(sel)
        if l.count(): l.first.click(); page.wait_for_load_state("networkidle")
    page.wait_for_selector("input[name='username']", timeout=20_000)
    page.fill("input[name='username']", USER); page.fill("input[name='password']", PW)
    page.click("button[type='submit'], input[type='submit']"); page.wait_for_load_state("networkidle")
    a = page.locator("input[name='approve']")
    if a.count(): a.first.click(); page.wait_for_load_state("networkidle")
    page.wait_for_selector("button.tab", timeout=30_000)


with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(ignore_https_errors=True, color_scheme="light", viewport={"width": 1440, "height": 1100})
    p = ctx.new_page(); login(p)
    head = p.evaluate("() => (document.body.innerText.match(/v[\\d.]+ · [0-9a-f]+/)||[])[0]")
    p.goto(f"{BASE}/#page=clusters", wait_until="networkidle")
    p.wait_for_selector("#cc-findings", timeout=30_000)
    p.wait_for_timeout(1500)
    result = {"head": head, "cards": {}}
    for i, name in enumerate(CLUSTERS, start=1):
        card = p.locator(f"#cc-cluster-{name}")
        card.wait_for(timeout=30_000)
        card.scroll_into_view_if_needed(); p.wait_for_timeout(300)
        card.screenshot(path=str(OUT / f"{i:02d}-card-{name}.png"))
        result["cards"][name] = card.inner_text()
    findings = p.locator("#cc-findings")
    findings.scroll_into_view_if_needed(); p.wait_for_timeout(300)
    findings.screenshot(path=str(OUT / f"{len(CLUSTERS) + 1:02d}-findings.png"))
    result["findings"] = findings.inner_text()
    p.screenshot(path=str(OUT / f"{len(CLUSTERS) + 2:02d}-tab-full.png"), full_page=True)
    (OUT / "shot.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    br.close()
