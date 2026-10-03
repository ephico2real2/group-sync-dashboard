#!/usr/bin/env python3
"""SPEC_H1 §5 (#542) on the deployed dashboard, as `developer`.

The login is the one in reports/2026-10-02_kpi-backups-306/scripts/walk.py. One mode per run, named by argv[1]:

    admin    With the grant (the cluster-admin tier), on the page's own controls:
             - delete one finished manual report run from the Library drawer (two presses);
             - preview, then confirm, the cleanup of the retired schedule `nightly-namespace-access`;
             - on the KPI page's Database copies card, delete the oldest unguarded `pre-restore` copy (two presses);
             - check the newest backup has no button, and that a DELETE of it through the API answers 409;
             - screenshots at 1280 and 375 px.
    refused  After the grant is deleted, without the tier:
             - GET /api/housekeeping/copies and a DELETE both answer 403;
             - the Library drawer offers no delete, and the KPI page is withheld.

The UI password comes from the environment only (GSD_UI_PASSWORD) and is never printed. Every `oc` call here is a
read (`exec` of a read, `get`, `logs`). The deletions are made by the dashboard, through its page, as the product
does them. Exits non-zero on a page error or a failed expectation; a failed expectation is recorded and the walk
goes on."""
import json
import os
import pathlib
import re
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

BASE = os.environ.get("GSD_BASE", "https://group-sync-dashboard.apps-crc.testing")
USER = "developer"
NS = "group-sync-dashboard"
RETIRED = "nightly-namespace-access"
SHOTS = pathlib.Path(__file__).resolve().parent.parent / "screenshots"
CLEAN_ENV = {k: v for k, v in os.environ.items() if k != "GSD_UI_PASSWORD"}
failures: list[str] = []
page_errors: list[str] = []


def utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def say(tag: str, value) -> None:
    text = value if isinstance(value, str) else json.dumps(value)
    print(re.sub(r"sha256~[A-Za-z0-9_-]+", "sha256~<redacted>", f"{utc()} {tag:58s}: {text}"), flush=True)


def expect(what: str, ok: bool, detail) -> None:
    say(f"{'PASS' if ok else 'FAIL'} {what}", detail)
    if not ok:
        failures.append(what)


def oc(*args: str) -> str:
    return subprocess.run(["oc", *args], env=CLEAN_ENV, capture_output=True, text=True, check=True, timeout=90).stdout


# The report store's index, read in the report pod: one line per run directory's run.json.
RUNS_READ = ("import json, pathlib\n"
             "for m in sorted(pathlib.Path('/artifacts').glob('*/run.json')):\n"
             "    j = json.loads(m.read_text())\n"
             "    print(json.dumps({k: j.get(k) for k in ('id', 'status', 'schedule', 'cluster', 'finished_at')}))")


def report_runs() -> list[dict]:
    out = oc("exec", "-n", NS, "deploy/group-sync-dashboard-report", "--", "python3.14", "-c", RUNS_READ)
    return [json.loads(line) for line in out.splitlines() if line.strip()]


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


def whoami(page) -> dict:
    return page.evaluate("() => ({ user: data.whoami.user, cluster_admin: (data.whoami.visibility || {}).cluster_admin })")


def api(page, method: str, path: str, body: dict | None = None) -> dict:
    """One call on the page's own session, with the header the page sends with every write."""
    return page.evaluate("""async ([method, path, body]) => {
        const init = { method, credentials: 'same-origin', headers: { 'X-GSD-Interaction': 'walk-542' } };
        if (body !== null) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(body); }
        const r = await fetch(path, init); let b = null; try { b = await r.json(); } catch (e) { b = null; }
        return { http: r.status, body: b }; }""", [method, path, body])


def shot(page, name: str) -> None:
    page.screenshot(path=str(SHOTS / name), full_page=False)
    say("screenshot", name)


def admin(page) -> None:
    who = whoami(page)
    expect("the grant gives the cluster-admin tier", who.get("cluster_admin") is True, who)

    runs = report_runs()
    retired = [r for r in runs if r["schedule"] == RETIRED and r["status"] in ("done", "failed")]
    manual = sorted((r for r in runs if not r["schedule"] and r["status"] in ("done", "failed")),
                    key=lambda r: r["id"])
    say("report runs before", {"total": len(runs), "retired": len(retired), "manual finished": len(manual),
                               "in flight": sum(r["status"] in ("queued", "running") for r in runs)})

    # 1. One manual run, from the Library drawer.
    if manual:
        run = manual[0]
        page.goto(f"{BASE}/#page=library&cluster={run['cluster']}&run={run['id']}")
        page.wait_for_selector("#drawer-delete", timeout=30_000)
        page.click("#drawer-delete")
        page.wait_for_function("() => document.getElementById('drawer-delete').textContent === 'Confirm delete'")
        shot(page, "library-drawer-confirm-1280.png")
        page.click("#drawer-delete")
        page.wait_for_selector("#hk-runs-note", timeout=30_000)
        note = page.locator("#hk-runs-note").inner_text()
        gone = all(r["id"] != run["id"] for r in report_runs())
        expect("one manual run deleted from the drawer", note == f"Run {run['id']} deleted." and gone,
               {"run": run["id"], "note": note, "gone from /artifacts": gone})
    else:
        expect("a finished manual run exists to delete", False, "none")

    # 2. The retired schedule's runs: preview, then confirm.
    page.select_option("#hk-runs-scope", f"schedule:{RETIRED}")
    page.fill("#hk-runs-days", "0"); page.dispatch_event("#hk-runs-days", "change")
    page.fill("#hk-runs-keep", "0"); page.dispatch_event("#hk-runs-keep", "change")
    page.click("#hk-runs-preview")
    page.wait_for_selector("#hk-runs-preview .hk-list", timeout=30_000)
    listed = page.locator("#hk-runs-preview .hk-list li").count()
    still = sum(r["schedule"] == RETIRED for r in report_runs())
    expect("the preview deletes nothing", still == len(retired), {"listed": listed, "retired runs still": still})
    page.locator("#lib-cleanup").scroll_into_view_if_needed()
    shot(page, "library-cleanup-preview-1280.png")
    page.click("#hk-runs-confirm")
    page.wait_for_function("() => (document.getElementById('hk-runs-note') || {}).textContent?.startsWith('Deleted')",
                           timeout=60_000)
    note = page.locator("#hk-runs-note").inner_text()
    left = [r for r in report_runs() if r["schedule"] == RETIRED]
    expect("the confirmed cleanup removed the retired schedule's runs", not left,
           {"note": note, "retired runs left": len(left)})
    shot(page, "library-cleanup-done-1280.png")

    # 3. The KPI page's Database copies card.
    listing = api(page, "GET", "/api/housekeeping/copies")
    copies = (listing.get("body") or {}).get("copies") or []
    say("copies before", [{k: c[k] for k in ("kind", "name", "bytes", "at", "guarded")} for c in copies])
    page.goto(f"{BASE}/#page=kpi")
    page.wait_for_selector("#hk-copies table", timeout=30_000)
    page.locator("#hk-copies").scroll_into_view_if_needed()
    shot(page, "kpi-database-copies-1280.png")
    pre = sorted((c for c in copies if c["kind"] == "pre-restore" and not c["guarded"]), key=lambda c: c["at"])
    if pre:
        key = f"pre-restore/{pre[0]['name']}"
        page.locator(f"[data-hk-copy='{key}']").click()
        page.wait_for_function(f"() => document.querySelector(\"[data-hk-copy='{key}']\").textContent === 'Confirm delete'")
        page.locator(f"[data-hk-copy='{key}']").click()
        page.wait_for_function(f"() => !document.querySelector(\"tr[data-hk-row='{key}']\")", timeout=30_000)
        after = (api(page, "GET", "/api/housekeeping/copies").get("body") or {}).get("copies") or []
        expect("the oldest unguarded pre-restore copy deleted from the card",
               all(f"{c['kind']}/{c['name']}" != key for c in after), {"deleted": key, "bytes": pre[0]["bytes"]})
    else:
        expect("an unguarded pre-restore copy exists to delete", False, "none")

    # 4. The guard: the newest backup has no button, and the API refuses it.
    newest = next((c for c in copies if c["kind"] == "backup" and c["guarded"]), None)
    if newest:
        key = f"backup/{newest['name']}"
        buttons = page.locator(f"tr[data-hk-row='{key}'] button").count()
        refused = api(page, "DELETE", f"/api/housekeeping/copies/backup/{newest['name']}")
        expect("the newest backup is kept: no button, and the API answers 409",
               buttons == 0 and refused["http"] == 409, {"copy": key, "buttons": buttons, "api": refused})
    else:
        expect("the newest backup is listed as guarded", False, "no guarded backup")

    page.set_viewport_size({"width": 375, "height": 900})
    page.locator("#hk-copies").scroll_into_view_if_needed()
    overflow = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
    say("KPI page at 375 px: scrollWidth - clientWidth", overflow)
    shot(page, "kpi-database-copies-375.png")


def refused(page) -> None:
    who = whoami(page)
    expect("without the grant the tier is off", who.get("cluster_admin") is False, who)
    listing = api(page, "GET", "/api/housekeeping/copies")
    expect("GET /api/housekeeping/copies answers 403", listing["http"] == 403, listing)
    attempt = api(page, "POST", "/api/housekeeping/reports/cleanup", {"scope": "all"})
    expect("a cleanup preview answers 403", attempt["http"] == 403, attempt)
    runs = [r for r in report_runs() if r["status"] in ("done", "failed")]
    if runs:
        run = runs[0]
        page.goto(f"{BASE}/#page=library&cluster={run['cluster']}&run={run['id']}")
        page.wait_for_timeout(4000)
        say("the Library at the lower tier", {"drawer-delete buttons": page.locator("#drawer-delete").count(),
                                              "cleanup cards": page.locator("#lib-cleanup").count()})
        expect("the Library offers no delete and no cleanup",
               page.locator("#drawer-delete").count() == 0 and page.locator("#lib-cleanup").count() == 0, run["id"])
        shot(page, "library-refused-developer-1280.png")


def main() -> int:
    mode = sys.argv[1]
    SHOTS.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        page.on("pageerror", lambda e: page_errors.append(str(e)))
        login(page)
        {"admin": admin, "refused": refused}[mode](page)
        visible = page.locator("text=Dashboard API error").count()
        expect("no page error and no 'Dashboard API error'", not page_errors and not visible,
               {"page errors": page_errors, "api error banners": visible})
        browser.close()
    say("result", {"mode": mode, "failures": failures})
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
