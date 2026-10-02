#!/usr/bin/env python3
"""SPEC_E6 §5 on the deployed KPI page, as `developer` (the login after
reports/2026-09-30_release-2.0.0-walk/scripts/epicd.py). One mode per run, named by argv[1]:

    kpi      with the grant (the cluster-admin tier): the Backups card below System status, its state and tiles;
             T306-17 — the card's `[data-kpi="backup-last"] time[datetime]` and Failures tile read, then at once
             `gsd_backup_*` from /metrics in the pod (loopback) and through the route, compared in the same minute;
             step 4 — the schema tile against offset 60 of the newest copy (64 bytes read in the pod) and the
             pre-upgrade tile against the listing of /data/pre-upgrade; the card at 375, 768 and 1280 px in light and
             dark, `scrollWidth == clientWidth` measured for the page and the card each time
    refused  after the grant is deleted: the tier off, no KPIs tab, the KPI page's refusal card, and what
             GET /api/kpi answers on the session

The UI password comes from the environment only (GSD_UI_PASSWORD) and is never printed; oc runs without it. Nothing
here writes to the cluster: every oc call is `exec` of a read or a `get`. Exits non-zero on a page error, a visible
"Dashboard API error" or a failed expectation; a failed expectation is recorded and the walk goes on."""
import ast
import datetime as dt
import json
import os
import pathlib
import re
import ssl
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get("GSD_BASE", "https://group-sync-dashboard.apps-crc.testing")
USER = "developer"
NS = "group-sync-dashboard"
SHOTS = pathlib.Path(__file__).resolve().parent.parent / "screenshots"
CLEAN_ENV = {k: v for k, v in os.environ.items() if k != "GSD_UI_PASSWORD"}
CARD = '[data-card="backups"]'
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


def pod_python(code: str) -> str:
    """python3.14 -c <code> in the dashboard container: a read, never a write."""
    argv = ["oc", "exec", "-n", NS, "deploy/group-sync-dashboard", "-c", "dashboard", "--", "python3.14", "-c", code]
    return subprocess.run(argv, env=CLEAN_ENV, capture_output=True, text=True, check=True, timeout=60).stdout


METRICS_LOOPBACK = ("import urllib.request\n"
                    "for l in urllib.request.urlopen('http://127.0.0.1:8080/metrics').read().decode().splitlines():\n"
                    "    l.startswith('gsd_backup') and print(l)")

# The newest copy by mtime (the metric's rule), its 64-byte header read once, read-only.
SCHEMA_READ = ("import glob, os, struct, sys\n"
               "d = sys.argv[1]\n"
               "copies = sorted((os.stat(p).st_mtime, p) for p in glob.glob(os.path.join(d, 'gsd-*.db')))\n"
               "m, p = copies[-1]\n"
               "with open(p, 'rb') as f: h = f.read(64)\n"
               "print(p, h[:16].hex(), len(h), struct.unpack('>I', h[60:64])[0], repr(m), sep='|')")

PRE_LIST = ("import os\n"
            "d = '/data/pre-upgrade'\n"
            "print(sorted(os.listdir(d)) if os.path.isdir(d) else 'absent: ' + d)")


def metrics_samples(text: str) -> dict:
    return {line.split()[0]: float(line.split()[1]) for line in text.splitlines()
            if line.startswith("gsd_backup") and len(line.split()) == 2}


def route_metrics() -> str:
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE   # the lab's route certificate, as `curl -sk`
    body = urllib.request.urlopen(f"{BASE}/metrics", context=ctx, timeout=30).read().decode()
    return "\n".join(l for l in body.splitlines() if l.startswith("gsd_backup"))


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


def tabs(page) -> list[str]:
    return page.evaluate("() => [...document.querySelectorAll('nav.tabs .tab')].map((e) => e.innerText.trim())")


def api_kpi(page) -> dict:
    return page.evaluate("""async () => { const r = await fetch('/api/kpi', { credentials: 'same-origin' });
        if (!r.ok) return { http: r.status };
        const b = await r.json(); const d = ((b.system || {}).dashboard || {}).data || {};
        return { http: r.status, as_of: b.as_of, backups: d.backups, pre_upgrade: d.pre_upgrade }; }""")


def card(page) -> dict:
    return page.evaluate("""(sel) => {
        const c = document.querySelector(sel), st = c.querySelector('.bk-state');
        const tile = (id) => { const t = c.querySelector(`[data-kpi="${id}"]`); if (!t) return null;
            return { label: t.querySelector('.label').innerText, value: t.querySelector('.value').innerText.replace(/\\s+/g, ' '),
                     note: t.querySelector('.note').innerText.replace(/\\s+/g, ' '),
                     datetimes: [...t.querySelectorAll('time[datetime]')].map((e) => e.getAttribute('datetime')) }; };
        return { heading: c.querySelector('h2').innerText.replace(/\\s+/g, ' '), state: st.dataset.state,
                 badge: st.querySelector('.badge').innerText.trim(), detail: st.querySelector('.d').innerText.replace(/\\s+/g, ' '),
                 tiles: Object.fromEntries(['backup-last', 'backup-kept', 'backup-failures', 'backup-schema', 'backup-preupgrade']
                     .map((id) => [id, tile(id)])) }; }""", CARD)


def sections(page) -> list[str]:
    """The KPI page's card headings in document order, the first words of each h2."""
    return page.evaluate("""() => [...document.querySelectorAll('main section.card > h2')]
        .map((h) => (h.firstChild && h.firstChild.textContent || '').trim())""")


def no_api_error(page) -> None:
    expect("no visible 'Dashboard API error'", page.locator("text=Dashboard API error").count() == 0, "")


def mode_kpi(page) -> None:
    who = whoami(page)
    expect("whoami: developer with the cluster-admin tier", who == {"user": USER, "cluster_admin": True}, who)
    t = tabs(page)
    expect("the KPIs tab is offered", "KPIs" in t, t)
    page.locator("nav.tabs .tab", has_text=re.compile(r"^KPIs$")).first.click()
    page.wait_for_selector(f"{CARD} .bk-state", timeout=30_000)
    page.wait_for_timeout(500)
    order = sections(page)
    say("KPI page card headings, in order", order)
    i = order.index("Backups") if "Backups" in order else -1
    expect("the Backups card is directly below System status", i > 0 and order[i - 1] == "System status", order)
    no_api_error(page)

    # T306-17 and step 4, read back to back: the card, the payload, /metrics (pod, then route), the copy's header.
    c = card(page)
    t_card = time.time()
    say("the card (DOM)", c)
    payload = api_kpi(page)
    say("GET /api/kpi on the session: system.dashboard.data.{backups,pre_upgrade}", payload)
    loop = pod_python(METRICS_LOOPBACK)
    t_loop = time.time()
    say("/metrics in the pod (127.0.0.1:8080), gsd_backup_*", loop.strip().splitlines())
    route = route_metrics()
    t_route = time.time()
    say(f"{BASE}/metrics, gsd_backup_*", route.splitlines())
    m_loop, m_route = metrics_samples(loop), metrics_samples(route)
    span = max(t_loop, t_route) - t_card
    expect("the card and both /metrics reads within the same minute", span < 60, f"{span:.1f} s from the card read")
    expect("the pod's and the route's gsd_backup_* agree", m_loop == m_route, {"pod": m_loop, "route": m_route})

    last = c["tiles"]["backup-last"] or {}
    card_dt = (last.get("datetimes") or [None])[0]
    ts = m_loop.get("gsd_backup_last_success_timestamp_seconds")
    metric_dt = dt.datetime.fromtimestamp(int(ts), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if ts else None
    expect("T306-17 last copy: card time[datetime] == the metric truncated to the second, UTC",
           card_dt is not None and card_dt == metric_dt,
           {"card": card_dt, "metric": ts, "metric_utc_s": metric_dt})
    fail_tile = (c["tiles"]["backup-failures"] or {}).get("value")
    fail_metric = m_loop.get("gsd_backup_failures_total")
    expect("T306-17 failures: the Failures tile == gsd_backup_failures_total",
           fail_tile is not None and fail_metric is not None and int(fail_tile.replace(",", "")) == int(fail_metric),
           {"tile": fail_tile, "metric": fail_metric})

    bdir = (payload.get("backups") or {}).get("dir") or "/data/backup"
    head = pod_python(SCHEMA_READ.replace("sys.argv[1]", repr(bdir))).strip().split("|")
    say(f"newest copy under {bdir}: path, header[:16], bytes read, offset 60 (big-endian u32), mtime", head)
    schema_tile = (c["tiles"]["backup-schema"] or {}).get("value", "")
    expect("step 4: the header is SQLite's", bytes.fromhex(head[1]) == b"SQLite format 3\x00" and head[2] == "64", head[1:3])
    expect("step 4: the schema tile's newest_schema == offset 60 of the newest copy",
           schema_tile.split("/")[0].strip() == head[3], {"tile": schema_tile, "offset_60": head[3]})
    expect("step 4: the newest copy by mtime is the card's last copy",
           metric_dt is not None and abs(float(head[4]) - ts) < 1e-3, {"mtime": head[4], "metric": ts})
    pre = pod_python(PRE_LIST).strip()
    say("/data/pre-upgrade in the pod", pre)
    pre_tile = (c["tiles"]["backup-preupgrade"] or {}).get("value")
    if pre.startswith("absent") or not any(n.startswith("pre-upgrade-") and n.endswith(".db") for n in ast.literal_eval(pre)):
        expect("step 4: no pre-upgrade copy on the volume, the tile reads 'none'", pre_tile == "none", {"tile": pre_tile})
    else:
        say("step 4: pre-upgrade copies present; the tile", c["tiles"]["backup-preupgrade"])
    expect("step 2: the state is healthy (the newest copy is under 12 h old)",
           c["state"] == "ok" and c["badge"] == "healthy", {"state": c["state"], "badge": c["badge"]})

    # Step 2's renders: the card at three widths in both themes; the context shot at 1280 light.
    for theme in ("light", "dark"):
        page.evaluate("(t) => document.documentElement.setAttribute('data-theme', t)", theme)
        for width in (375, 768, 1280):
            page.set_viewport_size({"width": width, "height": 900})
            page.wait_for_timeout(400)
            state = page.locator(f"{CARD} .bk-state").get_attribute("data-state")
            doc = page.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]")
            box = page.evaluate("(s) => { const c = document.querySelector(s); return [c.scrollWidth, c.clientWidth]; }", CARD)
            name = f"kpi-backups-{width}-{theme}.png"
            page.locator(CARD).screenshot(path=str(SHOTS / name))
            expect(f"{width} px {theme}: no horizontal scroll (page and card)",
                   doc[0] == doc[1] and box[0] <= box[1],
                   {"state": state, "page_scroll_client": doc, "card_scroll_client": box, "shot": f"screenshots/{name}"})
            if width == 1280 and theme == "light":
                # Page coordinates (the client rect plus the scroll), as a full-page clip takes them.
                top, bottom = page.evaluate("""(s) => { const y = (e) => e.getBoundingClientRect().top + scrollY;
                    const sys = [...document.querySelectorAll('main section.card.kpi-page')][0], c = document.querySelector(s);
                    return [y(sys), y(c) + c.getBoundingClientRect().height]; }""", CARD)
                page.screenshot(path=str(SHOTS / "kpi-system-status-and-backups-1280-light.png"), full_page=True,
                                clip={"x": 0, "y": max(0, top - 8), "width": 1280, "height": bottom - top + 16})
                say("context shot (System status above Backups)", "screenshots/kpi-system-status-and-backups-1280-light.png")
    page.evaluate("() => document.documentElement.setAttribute('data-theme', 'light')")


def mode_refused(page) -> None:
    who = whoami(page)
    expect("whoami: developer without the cluster-admin tier", who.get("user") == USER and who.get("cluster_admin") is not True, who)
    t = tabs(page)
    expect("the KPIs tab is not offered", "KPIs" not in t, t)
    page.goto(f"{BASE}/#page=kpi", wait_until="networkidle")
    page.wait_for_selector("main .scope-refusal", timeout=30_000)
    text = page.locator("main section.card").first.inner_text()
    say("the KPI page as rendered", re.sub(r"\s+", " ", text))
    expect("the KPI page is the refusal card", text.startswith("KPIs") and "For administrators only." in text, "")
    expect("no Backups card on the page", page.locator(CARD).count() == 0, page.locator(CARD).count())
    r = api_kpi(page)
    expect("GET /api/kpi on the session answers 403", r.get("http") == 403, r)
    page.screenshot(path=str(SHOTS / "kpi-refused-developer-1280-light.png"))
    say("shot", "screenshots/kpi-refused-developer-1280-light.png")
    no_api_error(page)


def main() -> int:
    mode = sys.argv[1]
    SHOTS.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        page.on("pageerror", lambda e: page_errors.append(str(e)))
        say("mode", mode)
        login(page)
        say("logged in", BASE)
        {"kpi": mode_kpi, "refused": mode_refused}[mode](page)
        browser.close()
    expect("no page errors", not page_errors, page_errors)
    say("failures", failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
