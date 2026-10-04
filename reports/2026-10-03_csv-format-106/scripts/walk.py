#!/usr/bin/env python3
"""SPEC_F2 §5 (#106, CSV as a report format) on the deployed dashboard, as `developer` under the walk's grant.

On the page's own controls, cluster `dashboard`, report `groups`:
  - the form shows a CSV box, unticked (screenshot at 1280 and 375 px);
  - tick CSV, untick PDF, flip the rosters switch: the boxes survive the repaint (the review's T106-10, live);
  - Generate; the run finishes with a "Download .csv" button; the CSV downloads through the page;
  - the Library drawer of that run offers `.csv` with its size;
  - the downloaded file: the BOM first, `Report,<title>`, `sha256 of the report data,<sha>` equal to the run record,
    page one marked not sealed, every record CRLF-ended, and Python's csv module reads it.

The UI password comes from the environment only (GSD_UI_PASSWORD) and is never printed. Every `oc` call is a read.
The run is the product's, made through its page. Exits non-zero on a page error or a failed expectation."""
import csv
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

BASE = os.environ.get("GSD_BASE", "https://group-sync-dashboard.apps-crc.testing")
USER, NS, CLUSTER, REPORT = "developer", "group-sync-dashboard", "dashboard", "groups"
HERE = pathlib.Path(__file__).resolve().parent.parent
SHOTS, FILES = HERE / "screenshots", HERE / "artefacts"
CLEAN_ENV = {k: v for k, v in os.environ.items() if k != "GSD_UI_PASSWORD"}
failures: list[str] = []
page_errors: list[str] = []


def utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def say(tag: str, value) -> None:
    text = value if isinstance(value, str) else json.dumps(value)
    print(re.sub(r"sha256~[A-Za-z0-9_-]+", "sha256~<redacted>", f"{utc()} {tag:60s}: {text}"), flush=True)


def expect(what: str, ok: bool, detail) -> None:
    say(f"{'PASS' if ok else 'FAIL'} {what}", detail)
    if not ok:
        failures.append(what)


def run_record(run_id: str) -> dict:
    """The run's own run.json, read in the report pod."""
    code = f"import pathlib; print(pathlib.Path('/artifacts/{run_id}/run.json').read_text())"
    out = subprocess.run(["oc", "exec", "-n", NS, "deploy/group-sync-dashboard-report", "--", "python3.14", "-c", code],
                         env=CLEAN_ENV, capture_output=True, text=True, check=True, timeout=90).stdout
    return json.loads(out)


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


def main() -> int:
    SHOTS.mkdir(exist_ok=True); FILES.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1280, "height": 900}, ignore_https_errors=True, accept_downloads=True)
        page = ctx.new_page()
        page.on("pageerror", lambda e: page_errors.append(str(e)))
        login(page)
        say("whoami", page.evaluate("() => ({ user: data.whoami.user, visibility: data.whoami.visibility })"))
        page.goto(f"{BASE}/#page=reports&cluster={CLUSTER}&report={REPORT}", wait_until="networkidle")
        page.wait_for_selector("#report-want-csv", timeout=30_000)
        expect("the CSV box is there, unticked", not page.is_checked("#report-want-csv"),
               {f: page.is_checked(f"#report-want-{f}") for f in ("pdf", "html", "csv") if page.locator(f"#report-want-{f}").count()})
        page.locator("#report-generate").scroll_into_view_if_needed()
        page.screenshot(path=str(SHOTS / "01-form-csv-unticked-1280.png"), full_page=True)

        page.check("#report-want-csv")
        if page.locator("#report-want-pdf").count():
            page.uncheck("#report-want-pdf")
        switch = page.locator('[data-switch="include_members"]')
        if switch.count():
            switch.first.click()
            page.wait_for_timeout(500)
        boxes = {f: page.is_checked(f"#report-want-{f}") for f in ("pdf", "html", "csv") if page.locator(f"#report-want-{f}").count()}
        expect("the boxes survive the form's repaint", boxes.get("csv") is True and boxes.get("pdf") is False, boxes)
        if switch.count():
            switch.first.click()                            # back to the default rosters setting
            page.wait_for_timeout(500)
        page.locator("#report-generate").scroll_into_view_if_needed()
        page.screenshot(path=str(SHOTS / "02-form-csv-ticked-1280.png"), full_page=True)

        with page.expect_request(lambda r: r.url.endswith("/api/runs") and r.method == "POST") as info:
            page.click("#report-generate")
        posted = json.loads(info.value.post_data)
        expect("Generate posts csv", "csv" in posted.get("formats", []), posted.get("formats"))
        button = page.locator('[data-format="csv"]').first
        button.wait_for(timeout=180_000)
        run_id = button.get_attribute("data-artifact")
        say("run", run_id)
        page.screenshot(path=str(SHOTS / "03-run-done-download-csv-1280.png"), full_page=True)
        with page.expect_download(timeout=60_000) as dl:
            button.click()
        target = FILES / dl.value.suggested_filename
        dl.value.save_as(str(target))
        say("downloaded", {"file": target.name, "bytes": target.stat().st_size})

        record = run_record(run_id)
        say("run record", {k: record.get(k) for k in ("id", "status", "formats", "sha256", "snapshot_stamp", "bytes")})
        raw = target.read_bytes()
        text = raw.decode("utf-8")
        expect("the file starts with the UTF-8 BOM", raw[:3] == b"\xef\xbb\xbf", raw[:3].hex())
        body = text[1:]
        expect("every record ends CRLF", body.endswith("\r\n") and "\n" not in body.replace("\r\n", ""),
               {"lines": body.count("\r\n")})
        records = list(csv.reader(io.StringIO(body, newline="")))
        expect("record 1 is the title", records[0][0] == "Report", records[0])
        expect("record 2 is the sealed sha256, equal to the run record",
               records[1] == ["sha256 of the report data", record.get("sha256")], records[1])
        sections = [r for r in records if r and r[0] == "Section"]
        expect("page one is the first section, not sealed",
               sections and sections[0] == ["Section", "Provenance and coverage", "not sealed: states the run"],
               sections[:1])
        expect("every other section is sealed", all(r[2] == "sealed" for r in sections[1:]), [r[1] for r in sections])
        tables = [r[1] for r in records if r and r[0] == "Table"]
        say("tables in the file", tables)
        expect("the file holds the report's tables", len(tables) > 0, len(tables))
        expect("the run stored csv", "csv" in (record.get("bytes") or {}), record.get("bytes"))

        page.goto(f"{BASE}/#page=library", wait_until="networkidle")
        card = page.locator(f'[data-artifact="{run_id}"]').first
        card.wait_for(timeout=30_000)
        page.locator(f'[id="lib-{run_id}-csv"]').scroll_into_view_if_needed()
        expect("the Library card offers .csv", page.locator(f'[id="lib-{run_id}-csv"]').count() == 1, f"#lib-{run_id}-csv")
        page.screenshot(path=str(SHOTS / "04-library-card-csv-1280.png"), full_page=False)

        page.set_viewport_size({"width": 375, "height": 812})
        page.goto(f"{BASE}/#page=reports&cluster={CLUSTER}&report={REPORT}", wait_until="networkidle")
        page.wait_for_selector("#report-want-csv", timeout=30_000)
        page.locator("#report-generate").scroll_into_view_if_needed()
        overflow = page.evaluate("() => document.documentElement.scrollWidth > window.innerWidth")
        expect("no sideways scroll at 375 px", not overflow, overflow)
        page.screenshot(path=str(SHOTS / "05-form-375.png"), full_page=False)
        expect("no page errors", not page_errors, page_errors)
        ctx.close(); browser.close()
    say("result", {"failures": failures})
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
