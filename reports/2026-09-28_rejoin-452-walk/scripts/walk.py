#!/usr/bin/env python3
"""#452 on the deployed dashboard, as `developer`: a Rejoin over a Secret that carries its own
`ldapConnectionBootstrap` keeps the cluster served. Adapted from reports/2026-09-27_rejoin-walk/scripts/walk.py.

    walk.py walk     step 4  (lab.sh apply and lab.sh grant ran first, and the tier cache was waited out)
                             the row polls auth_failed; Refresh answers auth_failed and offers Rejoin...;
                             Rejoin as developer: rejoined
                     step 5  the row stays (not retired), carries no finding, polls ok; Refresh answers connected;
                             the card at 1280, 768 and 375 px once its CONNECTION row reads ok
    walk.py after    a fresh login once the binding is gone: the tier the dashboard now answers

The password comes from the environment only and is never printed: GSD_UI_PASSWORD (developer's, from `crc console`).
The dialog is screenshotted only with its password field empty (asserted by its length, never read). Subprocesses
(capture.sh, oc) get an environment without it. The run exits non-zero on an uncaught page error, a visible
"Dashboard API error", or a failed expectation, and stops at the first failed step."""
import json, os, pathlib, re, subprocess, sys, time
from playwright.sync_api import sync_playwright

BASE = os.environ.get("GSD_BASE", "https://group-sync-dashboard.apps-crc.testing")
USER = "developer"
CID = "walk-452"
SECRET = f"gsd-cluster-{CID}"
HERE = pathlib.Path(__file__).resolve().parent
SHOTS = HERE.parent / "screenshots"
WIDTHS = [(1280, 900), (768, 1024), (375, 812)]
CLEAN_ENV = {k: v for k, v in os.environ.items() if k != "GSD_UI_PASSWORD"}
failures: list[str] = []
shot_n = [0]


class Stop(Exception):
    """A step answered differently from the brief: the walk stops here."""


def utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def say(tag: str, value) -> None:
    text = value if isinstance(value, str) else json.dumps(value)
    print(f"{utc()} {tag:40s}: {re.sub(r'sha256~[A-Za-z0-9_-]+', 'sha256~<redacted>', text)}", flush=True)


def expect(what: str, ok: bool, detail) -> None:
    say(f"{'PASS' if ok else 'FAIL'} {what}", detail)
    if not ok:
        failures.append(what)
        raise Stop(what)


def sh(*args: str) -> str:
    """A command with the password removed from its environment; its output, stripped."""
    r = subprocess.run(args, env=CLEAN_ENV, capture_output=True, text=True, timeout=180)
    return (r.stdout + r.stderr).strip()


def capture(kind: str, label: str, *extra: str) -> None:
    say("capture", sh(str(HERE / "capture.sh"), kind, label, *extra).splitlines()[-1])


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
    return page.evaluate("() => ({ user: data.whoami.user, tier: data.whoami.tier,"
                         " cluster_admin: (data.whoami.visibility || {}).cluster_admin })")


def api_view(page) -> dict:
    """The row, every finding naming the Secret, and every warning naming the cluster, from one read."""
    return page.evaluate("""async ([cid, secret]) => { const r = await fetch('/api/clusterconfigs?walk=1', { credentials: 'same-origin' });
        if (!r.ok) return { http: r.status };
        const d = await r.json();
        const c = (d.clusters || []).find((x) => x.id === cid);
        const row = c ? { id: c.id, enabled: c.enabled, retired: c.retired || false, api_url: c.api_url, source: c.source,
                          credential: c.credential, status: c.status, rejoinable: c.rejoinable, error: c.error || null } : null;
        return { http: r.status, row,
                 findings: (d.findings || []).filter((f) => JSON.stringify(f).includes(secret) || JSON.stringify(f).includes(cid)),
                 warnings: (d.warnings || []).filter((w) => JSON.stringify(w).includes(cid)),
                 fleet_accounts: ((d.fleet || {}).accounts || []).length,
                 fleet_names_walk_account: JSON.stringify((d.fleet || {}).accounts || []).includes('walk-bootstrap-452') }; }""",
                         [CID, SECRET])


def card_facts(page) -> dict | None:
    return page.evaluate("""(cid) => { const c = document.getElementById('cc-cluster-' + cid);
        if (!c) return null;
        const t = (id) => { const e = document.getElementById(id); return e ? e.innerText.replace(/\\s+/g, ' ').trim() : null; };
        const rj = document.getElementById('cc-rejoin-' + cid);
        return { refresh: t('cc-refresh-result-' + cid), rejoin: t('cc-rejoin-result-' + cid),
                 rejoin_button: rj ? { text: rj.innerText.trim(), disabled: rj.disabled } : null }; }""", CID)


def dialog_facts(page) -> dict:
    """The dialog's state; the password field by its LENGTH only, never its value."""
    return page.evaluate("""() => { const d = document.getElementById('rejoin-dialog');
        return { open: d.open, cluster: d.dataset.cluster || null,
                 username_length: document.getElementById('rejoin-username').value.length,
                 password_length: document.getElementById('rejoin-password').value.length,
                 password_type: document.getElementById('rejoin-password').type,
                 message: document.getElementById('rejoin-msg').innerText.trim() }; }""")


def shot(page, selector: str, name: str) -> None:
    """One capture per width, all on this page: the view state (the Refresh and Rejoin answers) survives a resize."""
    for width, height in WIDTHS:
        page.set_viewport_size({"width": width, "height": height})
        page.wait_for_timeout(400)
        if selector == "#rejoin-dialog":
            assert dialog_facts(page)["password_length"] == 0, "the dialog is never captured with a typed password"
        el = page.locator(selector)
        el.scroll_into_view_if_needed(); page.wait_for_timeout(200)
        shot_n[0] += 1
        fname = f"{shot_n[0]:02d}-{width}-{name}.png"
        el.screenshot(path=str(SHOTS / fname))
        say("shot", fname)
    page.set_viewport_size({"width": 1280, "height": 900})
    page.wait_for_timeout(300)


def open_clusters(page) -> None:
    page.goto(BASE + "/#page=clusters", wait_until="networkidle")
    page.wait_for_selector("#cc-head", timeout=30_000)
    page.wait_for_selector("[data-cc-cluster]", timeout=30_000)
    page.wait_for_timeout(1000)


def no_api_error(page, where: str) -> None:
    n = page.locator("text=Dashboard API error").count()
    expect(f"no 'Dashboard API error' ({where})", n == 0, n)


def press_refresh(page) -> dict:
    page.click(f"#cc-refresh-{CID}")
    page.wait_for_function("(cid) => { const r = document.getElementById('cc-refresh-result-' + cid);"
                           " return r && !/probing/.test(r.innerText); }", arg=CID, timeout=60_000)
    return card_facts(page)


def press_rejoin(page) -> tuple[dict, dict]:
    """Type developer and the password into the open dialog, press once, wait for the answer."""
    page.fill("#rejoin-username", USER)
    page.fill("#rejoin-password", os.environ["GSD_UI_PASSWORD"])
    t = utc()
    page.click("#rejoin-go")
    page.wait_for_function("(cid) => { const r = document.getElementById('cc-rejoin-result-' + cid);"
                           " return r && !/signing in once/.test(r.innerText); }", arg=CID, timeout=90_000)
    page.wait_for_timeout(500)
    card, dlg = card_facts(page), dialog_facts(page)
    say("rejoin pressed at", t)
    say("rejoin answer on the card", card["rejoin"])
    say("dialog after the answer", dlg)
    return card, dlg


def open_dialog(page) -> None:
    page.click(f"#cc-rejoin-{CID}")
    page.wait_for_function("() => document.getElementById('rejoin-dialog').open", timeout=10_000)
    page.wait_for_timeout(300)


def connection_text(page) -> str | None:
    return page.evaluate("""(cid) => { const c = document.getElementById('cc-cluster-' + cid); if (!c) return null;
        const kv = [...c.querySelectorAll('.cc-kv')].find((k) => k.querySelector('.k').textContent.trim() === 'connection');
        if (!kv) return null;
        const t = kv.querySelector('.v').innerText.replace(/\\s+/g, ' ').trim();
        return t.split(' Refresh:')[0]; }""", CID)


def walk(page, errors: list) -> None:
    walk_start = utc()
    who = whoami(page)
    say("whoami", who)
    expect("developer holds the cluster-admin tier for the walk", who["cluster_admin"] is True, who)

    # --- step 4: the row before the Rejoin, Refresh, then Rejoin ----------------------------------------------
    open_clusters(page)
    no_api_error(page, "clusters tab")
    v = api_view(page)
    say("walk-452 before the Rejoin", v)
    expect("the row is served, polls auth_failed, is rejoinable, and carries no finding",
           bool(v.get("row")) and not v["row"]["retired"] and v["row"]["status"] == "auth_failed"
           and v["row"]["rejoinable"] is True and v["findings"] == [], v)
    expect("the made-up account is on no fleet-account view", v["fleet_names_walk_account"] is False, v)
    shot(page, f"#cc-cluster-{CID}", "step4-card-before")
    f = press_refresh(page)
    say("Refresh answered", f)
    expect("Refresh answers auth_failed and the card offers Rejoin…",
           (f["refresh"] or "").startswith("Refresh: auth_failed") and "use Rejoin" in (f["refresh"] or "")
           and f["rejoin_button"] == {"text": "Rejoin…", "disabled": False}, f)
    shot(page, f"#cc-cluster-{CID}", "step4-card-offers-rejoin")
    open_dialog(page)
    d = dialog_facts(page)
    say("dialog opened", d)
    expect("the dialog opens for walk-452, both fields empty, the password field type=password",
           d["open"] and d["cluster"] == CID and d["username_length"] == 0 and d["password_length"] == 0
           and d["password_type"] == "password", d)
    shot(page, "#rejoin-dialog", "step4-dialog-empty")
    card, dlg = press_rejoin(page)
    expect("Rejoin answers rejoined and the dialog closes",
           (card["rejoin"] or "").startswith("Rejoin: rejoined") and not dlg["open"]
           and dlg["password_length"] == 0 and dlg["username_length"] == 0, [card["rejoin"], dlg])
    shot(page, f"#cc-cluster-{CID}", "step4-rejoined")
    capture("secret", "step5-after-rejoin")

    # --- step 5: THE CHECK — the rejoined Secret stays served ----------------------------------------------------
    deadline, v = time.time() + 240, None
    while time.time() < deadline:
        v = api_view(page)
        if v.get("row") and v["row"]["status"] == "ok":
            break
        page.wait_for_timeout(5_000)
    say("walk-452 after the Rejoin", v)
    expect("the row stays served (not retired) with no finding, and polls ok",
           bool(v.get("row")) and not v["row"]["retired"] and v["findings"] == [] and v["row"]["status"] == "ok", v)
    f = press_refresh(page)
    say("Refresh after the Rejoin", f)
    expect("Refresh answers connected, the Rejoin answer still shown",
           bool(re.match(r"^Refresh: connected · \d{4}-\d{2}-\d{2}T", f["refresh"] or ""))
           and (f["rejoin"] or "").startswith("Rejoin: rejoined"), f)
    shot(page, f"#cc-cluster-{CID}", "step5-refresh-connected")
    # The card's CONNECTION row is redrawn on the page's own poll (60 s, #316's observation (b)): wait for it
    deadline, seen = time.time() + 150, connection_text(page)
    while time.time() < deadline and not (seen or "").startswith("ok"):
        page.wait_for_timeout(5_000)
        seen = connection_text(page)
    say("CONNECTION row", [utc(), seen])
    expect("the card's CONNECTION row reads ok", (seen or "").startswith("ok"), seen)
    v = api_view(page)
    say("walk-452 at the end of step 5", v)
    expect("still served, no finding", bool(v.get("row")) and not v["row"]["retired"] and v["findings"] == [], v)
    shot(page, f"#cc-cluster-{CID}", "step5-card-served")
    capture("secret", "step5-end"); capture("tokens", "step5-end")
    capture("podlog", "step5", walk_start)
    no_api_error(page, "end of step 5")
    expect("no uncaught page errors", not errors, errors)


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "walk"
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        login(page)
        if mode == "after":
            who = whoami(page)
            status = page.evaluate("async () => (await fetch('/api/clusterconfigs', { credentials: 'same-origin' })).status")
            say("whoami", who); say("/api/clusterconfigs", status)
            try:
                expect("after the binding's removal: no cluster-admin tier, /api/clusterconfigs 403",
                       who["cluster_admin"] is False and status == 403, [who, status])
            except Stop:
                pass
        else:
            try:
                walk(page, errors)
            except Stop as e:
                say("STOPPED at", str(e))
            except Exception as e:  # noqa: BLE001 — a walk defect is reported, then the shell cleans up
                failures.append(f"exception: {type(e).__name__}")
                say("STOPPED on an exception", f"{type(e).__name__}: {e}")
        br.close()
    say("failures", failures)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
