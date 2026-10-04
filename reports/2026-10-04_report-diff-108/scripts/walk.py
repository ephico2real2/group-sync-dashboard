#!/usr/bin/env python3
"""SPEC_F3 §5 (#108, report-diff runs) on the deployed dashboard, as `developer` under the walk's grant.

    walk.py <head run id> <base run id> <tag> <expect: none|planted>

On the Reporting status page's Report history: press "Diff vs…" on the head's row, check the picker pre-selects the
base (the newest earlier finished run of the same report and cluster), Generate diff, wait for the diff run, and
download its .json through the page. `none`: the diff must read "No change" (no changed block, totals zero).
`planted`: the only change must be rows added that name the planted binding's group, and nothing removed.
Screenshots go to ../screenshots/<tag>-*.png, the .json to ../artefacts/. The UI password comes from the environment
only (GSD_UI_PASSWORD). Exits non-zero on a page error or a failed expectation."""
import json
import os
import pathlib
import re
import sys
import time

from playwright.sync_api import sync_playwright

BASE = os.environ.get("GSD_BASE", "https://group-sync-dashboard.apps-crc.testing")
USER, CLUSTER, GROUP = "developer", "dashboard", "app-ocp-rbac-demo-ns-admin"
HERE = pathlib.Path(__file__).resolve().parent.parent
SHOTS, FILES = HERE / "screenshots", HERE / "artefacts"
failures: list[str] = []
page_errors: list[str] = []


def say(tag: str, value) -> None:
    text = value if isinstance(value, str) else json.dumps(value)
    print(re.sub(r"sha256~[A-Za-z0-9_-]+", "sha256~<redacted>",
                 f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {tag:56s}: {text}"), flush=True)


def expect(what: str, ok: bool, detail) -> None:
    say(f"{'PASS' if ok else 'FAIL'} {what}", detail)
    if not ok:
        failures.append(what)


def login(page) -> None:
    page.goto(BASE, wait_until="networkidle")
    b = page.locator("button:has-text('Log in with OpenShift')")
    if b.count(): b.first.click(); page.wait_for_load_state("networkidle")
    c = page.locator("a:has-text('developer')")           # CRC's htpasswd identity provider is named `developer`
    if c.count(): c.first.click(); page.wait_for_load_state("networkidle")
    page.wait_for_selector("input[name='username']", timeout=20_000)
    page.fill("input[name='username']", USER)
    page.fill("input[name='password']", os.environ["GSD_UI_PASSWORD"])
    page.click("button[type='submit'], input[type='submit']"); page.wait_for_load_state("networkidle")
    a = page.locator("input[name='approve']")
    if a.count(): a.first.click(); page.wait_for_load_state("networkidle")
    page.wait_for_function("() => typeof data !== 'undefined' && data.whoami && data.whoami.authenticated",
                           timeout=30_000)


def changed_blocks(doc: dict) -> list[dict]:
    """The diff's Removed/Added pairs: every sealed section after Inputs and Summary."""
    out = []
    for s in doc["sections"]:
        if s["sealed"] and s["title"] not in ("Inputs", "Summary"):
            tables = {b["title"]: b for b in s["blocks"] if b["kind"] == "table"}
            out.append({"where": s["title"], "removed": tables["Removed"]["rows"], "added": tables["Added"]["rows"]})
    return out


def main() -> int:
    head, base, tag, want = sys.argv[1:5]
    SHOTS.mkdir(exist_ok=True); FILES.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1280, "height": 900}, ignore_https_errors=True, accept_downloads=True)
        page = ctx.new_page()
        page.on("pageerror", lambda e: page_errors.append(str(e)))
        login(page)
        page.goto(f"{BASE}/#page=reporting&cluster={CLUSTER}", wait_until="networkidle")
        page.wait_for_selector("#reporting-history tbody tr", timeout=30_000)
        button = page.locator(f'[data-diff="{head}"]')
        expect("the head's row offers Diff vs…", button.count() == 1, head)
        button.first.click()
        page.wait_for_selector("#history-diff-base", timeout=30_000)
        chosen = page.eval_on_selector("#history-diff-base", "el => el.value")
        expect("the picker pre-selects the newest earlier run", chosen == base, {"chosen": chosen, "base": base})
        page.locator("#history-diff").scroll_into_view_if_needed()
        page.screenshot(path=str(SHOTS / f"{tag}-1-picker.png"), full_page=False)
        page.click("#history-diff-go")
        done = page.locator('#history-diff [data-format="json"]')
        done.wait_for(timeout=180_000)
        diff_id = done.get_attribute("data-artifact")
        say("diff run", diff_id)
        page.locator("#history-diff").scroll_into_view_if_needed()
        page.screenshot(path=str(SHOTS / f"{tag}-2-diff-done.png"), full_page=False)
        with page.expect_download(timeout=60_000) as dl:
            done.click()
        target = FILES / f"{tag}-{dl.value.suggested_filename}"
        dl.value.save_as(str(target))
        doc = json.loads(target.read_text())
        blocks = changed_blocks(doc)
        say("diff params", doc["params"])
        say("diff totals", doc["totals"])
        say("changed blocks", blocks)
        expect("the diff names the head and base it compared", doc["params"].get("head") == head and doc["params"].get("base") == base,
               {k: doc["params"].get(k) for k in ("base", "head")})
        if want == "none":
            expect("No change: no changed block, totals zero", not blocks and not any(doc["totals"].values()), doc["totals"])
        else:
            # A binding also moves the counts derived from it (a findings tally, say): such a value shows as one row
            # removed and one added under the same key. Everything else must be the binding itself, added.
            removed = [r for b in blocks for r in b["removed"]]
            added = [r for b in blocks for r in b["added"]]
            moved_keys = {r[0] for r in removed}
            expect("every removed row is a value that moved under the same key",
                   all(any(a[0] == r[0] for a in added) for r in removed), removed)
            binding_rows = [a for a in added if a[0] not in moved_keys]
            expect("every other added row names the planted group",
                   bool(binding_rows) and all(GROUP in json.dumps(a) for a in binding_rows), binding_rows)
        expect("no page errors", not page_errors, page_errors)
        ctx.close(); browser.close()
    say("result", {"failures": failures})
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
