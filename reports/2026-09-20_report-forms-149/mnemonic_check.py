#!/usr/bin/env python3
"""Download the run the walk generated and show what `group_mnemonic: [alpha]` resolved to."""
import json, os, pathlib, sys
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from forms_walk import login, BASE  # noqa: E402  (module-level walk guarded below)

with sync_playwright() as p:
    br = p.chromium.launch(); ctx = br.new_context(ignore_https_errors=True, accept_downloads=True)
    page = ctx.new_page(); login(page)
    page.goto(BASE + "/#page=reporting&cluster=crc-local", wait_until="networkidle")
    page.wait_for_selector("#reporting-history tbody tr")
    row = page.locator("#reporting-history tbody tr").filter(has_text="access-certification").first
    with page.expect_download() as dl:
        row.locator('[data-artifact][data-format="json"]').click()
    doc = json.loads(pathlib.Path(dl.value.path()).read_bytes())
    params = doc.get("params") or doc.get("provenance", {}).get("params") or {}
    print("params  :", json.dumps(params))
    groups = [s["title"] for s in doc.get("sections", []) if s.get("title", "").startswith("Group:")]
    print("groups  :", groups)
    scope = [it for s in doc.get("sections", []) for b in s.get("blocks", []) for it in (b.get("items") or []) if it and it[0] == "Scope"]
    print("scope   :", scope)
    br.close()
