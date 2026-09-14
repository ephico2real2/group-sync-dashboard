#!/usr/bin/env python3
"""End-to-end walk of the deployed dashboard on CRC, with a screenshot per step.

Logs in through the real ingress (oauth-proxy → OpenShift OAuth → consent), visits every tab
the page offers, then exercises the report service: every enabled report in the catalogue is
generated (PDF + HTML), its status is captured, and its artefacts (pdf, html, json) are
downloaded through the page's own download path. Every measurement lands in results.json so
the document is built from what happened, not from recollection.

Refuses a broken page the way capture-screenshots.py does: an uncaught JavaScript error or a
visible "Dashboard API error" marks the step failed rather than producing a pretty image of a
broken page.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sys
import time

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

REQUIRED_PARAMS = {
    # namespace-access has no default; these namespaces exist on the reference cluster.
    "namespace-access": {"namespaces": "group-sync-dashboard,openshift-monitoring"},
    "access-certification": {"campaign": "E2E walk 2026-09-14", "due": "2026-10-15",
                             "reviewer": "kubeadmin"},
}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_of(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Walk:
    def __init__(self, page, out: pathlib.Path):
        self.page = page
        self.out = out
        self.steps: list[dict] = []
        self.errors: list[str] = []
        self.n = 0
        page.on("pageerror", lambda e: self.errors.append(str(e)))

    def shot(self, slug: str, full: bool = True) -> str:
        self.n += 1
        name = f"{self.n:02d}-{slug}.png"
        self.page.mouse.move(0, 0)
        self.page.evaluate("document.activeElement && document.activeElement.blur()")
        self.page.wait_for_timeout(150)
        self.page.screenshot(path=str(self.out / name), full_page=full)
        return name

    def record(self, step: str, ok: bool, detail: str, screenshot: str | None = None, **extra):
        row = {"t": now(), "step": step, "ok": ok, "detail": detail, "screenshot": screenshot}
        row.update(extra)
        self.steps.append(row)
        flag = "ok " if ok else "FAIL"
        print(f"  [{flag}] {step}: {detail}" + (f"  → {screenshot}" if screenshot else ""))

    def page_clean(self) -> str | None:
        if self.errors:
            return f"JavaScript error — {self.errors[0]}"
        if "Dashboard API error" in self.page.locator("body").inner_text():
            return "the page rendered an API error"
        return None


def login(w: Walk, base: str, user: str, password: str, provider: str) -> bool:
    page = w.page
    page.goto(base, wait_until="networkidle")
    shot = w.shot("oauth-proxy-interstitial")
    w.record("open the route", True, f"{base} → {page.url}", shot)

    interstitial = page.locator("button:has-text('Log in with OpenShift')")
    if interstitial.count():
        interstitial.first.click()
        page.wait_for_load_state("networkidle")
    chooser = page.locator(f"a:has-text('{provider}')")
    if chooser.count():
        shot = w.shot("openshift-idp-chooser")
        w.record("identity-provider chooser", True,
                 f"offered: {', '.join(t.strip() for t in page.locator('a').all_inner_texts() if t.strip())}; picked {provider}", shot)
        chooser.first.click()
        page.wait_for_load_state("networkidle")
    page.wait_for_selector("input[name='username']", timeout=20_000)
    page.fill("input[name='username']", user)
    page.fill("input[name='password']", password)
    shot = w.shot("openshift-login-form")
    w.record("OpenShift login form", True, f"username filled: {user}", shot)
    page.click("button[type='submit'], input[type='submit']")
    page.wait_for_load_state("networkidle")
    approve = page.locator("input[name='approve']")
    if approve.count():
        shot = w.shot("service-account-consent")
        w.record("service-account consent", True,
                 "the ServiceAccount is the OAuth client; approval_prompt=force shows this on every login", shot)
        approve.first.click()
        page.wait_for_load_state("networkidle")
    try:
        page.wait_for_selector("button.tab", timeout=20_000)
    except PWTimeout:
        w.record("login", False, f"did not reach the dashboard; page at {page.url}", w.shot("login-failed"))
        return False
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(800)
    w.record("login", True, f"dashboard rendered at {page.url}")
    return True


def api_json(w: Walk, path: str) -> dict | None:
    """A same-origin fetch from inside the page: the proxy cookie goes with it."""
    try:
        return w.page.evaluate(
            "async (p) => { const r = await fetch(p, {headers: {Accept: 'application/json'}});"
            " const t = await r.text(); let j = null; try { j = JSON.parse(t) } catch (e) {}"
            " return {status: r.status, json: j, text: t.slice(0, 400)}; }", path)
    except Exception as e:  # noqa: BLE001
        return {"status": None, "error": str(e)}


def walk_tabs(w: Walk):
    page = w.page
    labels = [t.strip() for t in page.locator("button.tab").all_inner_texts()]
    w.record("tab strip", True, f"{len(labels)} tabs: {', '.join(labels)}")
    for label in labels:
        if label == "Reports":
            continue  # exercised separately, below
        w.errors.clear()
        page.click(f'button.tab:text-is("{label}")')
        page.wait_for_selector(f'button.tab[aria-current="page"]:text-is("{label}")', timeout=15_000)
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("h2", timeout=15_000)
        page.wait_for_timeout(700)
        problem = w.page_clean()
        h2 = page.locator("h2").first.inner_text().strip()
        slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
        shot = w.shot(f"tab-{slug}")
        w.record(f"tab {label}", problem is None, problem or f"heading: {h2}", shot)


def walk_reports(w: Walk):
    page = w.page
    w.errors.clear()
    page.click('button.tab:text-is("Reports")')
    page.wait_for_selector('button.tab[aria-current="page"]:text-is("Reports")', timeout=15_000)
    page.wait_for_load_state("networkidle")
    try:
        page.wait_for_selector("#report-picker", timeout=20_000)
    except PWTimeout:
        w.record("Reports tab", False, "the picker never rendered", w.shot("reports-missing"))
        return
    page.wait_for_timeout(600)
    cat = page.evaluate("data.reportCatalog")
    reports = cat.get("reports", [])
    enabled = [r for r in reports if r.get("enabled")]
    pdf = cat.get("pdf") or {}
    shot = w.shot("reports-catalogue")
    w.record("Reports tab", w.page_clean() is None,
             f"{len(reports)} reports in the catalogue, {len(enabled)} enabled; PDF {'on, variant ' + str(pdf.get('variant')) if pdf.get('enabled') else 'off'}",
             shot, catalogue=[{"name": r["name"], "title": r["title"], "enabled": r["enabled"]} for r in reports])

    runs_dir = w.out / "reports"
    runs_dir.mkdir(exist_ok=True)
    for r in enabled:
        name = r["name"]
        w.errors.clear()
        page.click(f"#report-pick-{name}")
        page.wait_for_selector("#report-form", timeout=10_000)
        page.wait_for_timeout(300)
        # Required parameters without a default.
        for pname, val in REQUIRED_PARAMS.get(name, {}).items():
            sel = f"#report-param-{name}-{pname}"
            if page.locator(sel).count():
                page.fill(sel, val)
                page.locator(sel).dispatch_event("change")
        if page.locator("#report-want-pdf").count() and not page.locator("#report-want-pdf").is_checked():
            page.check("#report-want-pdf")
        if not page.locator("#report-want-html").is_checked():
            page.check("#report-want-html")
        shot = w.shot(f"report-{name}-form")
        w.record(f"report {name}: form", True,
                 f"{r['title']} — params {', '.join(p['name'] for p in r.get('params', [])) or '(none)'}", shot)

        t0 = time.monotonic()
        page.click("#report-generate")
        status_text = ""
        try:
            page.wait_for_function(
                "() => { const s = document.querySelector('#report-status');"
                " return s && /— (done|failed)/.test(s.innerText); }", timeout=120_000)
        except PWTimeout:
            w.record(f"report {name}: generate", False, "no terminal status within 120 s", w.shot(f"report-{name}-timeout"))
            continue
        elapsed = round(time.monotonic() - t0, 1)
        page.wait_for_timeout(400)
        run = page.evaluate("view.reportRun")
        status_text = page.locator("#report-status").inner_text().strip().replace("\n", " ")
        shot = w.shot(f"report-{name}-status")
        ok = run.get("status") == "done"
        w.record(f"report {name}: generate", ok,
                 f"run {run.get('id')} {run.get('status')} in {elapsed}s; formats {run.get('formats')}; sha256 {str(run.get('sha256'))[:16]}…; snapshot {run.get('snapshot_stamp')}"
                 + ("" if ok else f"; error: {run.get('error')}"),
                 shot, run=run, elapsed_s=elapsed, status_line=status_text)
        if not ok:
            continue
        for fmt in list(run.get("formats") or []) + ["json"]:
            btn = page.locator(f"#report-status [data-artifact='{run['id']}'][data-format='{fmt}']")
            if not btn.count():
                w.record(f"report {name}: download .{fmt}", False, "no download button")
                continue
            try:
                with page.expect_download(timeout=60_000) as dl:
                    btn.click()
                d = dl.value
                target = runs_dir / d.suggested_filename
                d.save_as(str(target))
                size = target.stat().st_size
                extra = {"file": str(target), "bytes": size}
                detail = f"{d.suggested_filename} ({size} bytes)"
                if fmt == "json":
                    extra["sha256_of_file"] = sha256_of(target)
                    detail += f"; sha256 of the file {extra['sha256_of_file'][:16]}…"
                if fmt == "pdf":
                    head = target.read_bytes()[:8]
                    extra["magic"] = head.decode("latin-1")
                    detail += f"; starts with {head[:5]!r}"
                w.record(f"report {name}: download .{fmt}", True, detail, **extra)
            except PWTimeout:
                w.record(f"report {name}: download .{fmt}", False, "no download event within 60 s")

    page.wait_for_timeout(500)
    runs = page.evaluate("data.reportRuns")
    shot = w.shot("reports-recent-runs")
    rows = (runs or {}).get("runs") or []
    w.record("Recent runs table", True, f"{len(rows)} runs listed" + (f" of {runs.get('total')}" if runs and runs.get("truncated") else ""), shot,
             runs=[{k: x.get(k) for k in ("id", "report", "cluster", "generated_by", "status", "requested_at")} for x in rows[:20]])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--login-user", required=True)
    ap.add_argument("--provider", default="developer")
    ap.add_argument("--out", required=True)
    ap.add_argument("--theme", default="dark")
    args = ap.parse_args()
    password = os.environ.get("GSD_UI_PASSWORD")
    if not password:
        print("GSD_UI_PASSWORD is required", file=sys.stderr)
        return 2
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1,
                                      color_scheme=args.theme, ignore_https_errors=True, accept_downloads=True)
        page = context.new_page()
        w = Walk(page, out)
        started = now()
        ok = login(w, args.base, args.login_user, password, args.provider)
        if ok:
            for path in ("/api/whoami", "/api/version", "/api/clusters", "/report/healthz", "/report/readyz"):
                res = api_json(w, path)
                body = res.get("json") if res.get("json") is not None else res.get("text")
                w.record(f"GET {path}", res.get("status") == 200, f"HTTP {res.get('status')}", api=body)
            walk_tabs(w)
            walk_reports(w)
        browser.close()

    summary = {
        "started": started, "finished": now(), "base": args.base, "login_user": args.login_user,
        "theme": args.theme, "steps": w.steps,
        "passed": sum(1 for s in w.steps if s["ok"]), "failed": sum(1 for s in w.steps if not s["ok"]),
    }
    (out / "results.json").write_text(json.dumps(summary, indent=2, default=str))
    print(f"\n{summary['passed']} steps passed, {summary['failed']} failed → {out}")
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
