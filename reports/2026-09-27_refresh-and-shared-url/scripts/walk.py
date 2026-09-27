#!/usr/bin/env python3
"""#311 (Refresh) and #314 (the shared API URL warning) on the deployed dashboard, as `developer`.

    walk.py walk    the Cluster Configurations tab at 1280, 768 and 375 px: the shared-API-URL banner, the chip and
                    hint on the entries that share the URL, no chip on the disabled entries at the same URL; then
                    Refresh on shared-rnd (idle, in flight, succeeded, and again after the 60-second repaint), and
                    Refresh on each enabled mock entry, to find a refusal the lab really has
    walk.py after   a fresh login once the walk's grant is removed: the tier the dashboard now answers

The password comes from the environment only (GSD_UI_PASSWORD); nothing here prints or stores it. The in-flight
state is held with Chromium's own network emulation (a 4 s latency on the Refresh request), not by any change to
the lab. Screenshots go to ../screenshots, the page's /api/clusterconfigs answer (selected fields) to ../evidence;
every printed line is a measurement the README quotes. Exits non-zero on an uncaught page error, a visible
"Dashboard API error", or a failed expectation."""
import json, os, pathlib, re, sys, time
from playwright.sync_api import sync_playwright

BASE = os.environ.get("GSD_BASE", "https://group-sync-dashboard.apps-crc.testing")
USER = "developer"
HERE = pathlib.Path(__file__).resolve().parent
SHOTS = HERE.parent / "screenshots"
EVIDENCE = HERE.parent / "evidence"
WIDTHS = [(1280, 900), (768, 1024), (375, 812)]
REFRESHED = "shared-rnd"
MOCKS = ["mock-privateca", "mock-selfsigned", "mock-trusted"]
failures: list[str] = []


def utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def say(tag: str, value) -> None:
    print(f"{utc()} {tag:34s}: {value if isinstance(value, str) else json.dumps(value)}", flush=True)


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


def whoami(page) -> dict:
    return page.evaluate("() => ({ user: data.whoami.user, tier: data.whoami.tier,"
                         " cluster_admin: (data.whoami.visibility || {}).cluster_admin })")


def shot(el, name: str) -> None:
    el.scroll_into_view_if_needed(); el.page.wait_for_timeout(300)
    el.screenshot(path=str(SHOTS / name))
    say("shot", name)


def card(page, cid: str):
    return page.locator(f"#cc-cluster-{cid}")


def card_facts(page, cid: str) -> dict:
    return page.evaluate("""(cid) => { const c = document.getElementById('cc-cluster-' + cid);
        if (!c) return null;
        const h2 = c.querySelector('h2'), hint = c.querySelector('.cc-shared-api-hint');
        const srv = [...c.querySelectorAll('.cc-kv')].find(k => k.querySelector('.k').textContent === 'server');
        const btn = c.querySelector('[data-cc-refresh]'), res = c.querySelector('#cc-refresh-result-' + cid);
        return { heading: h2.innerText.replace(/\\s+/g, ' ').trim(),
                 chip: /shared API URL/.test(h2.innerText), hint: hint ? hint.innerText.trim() : null,
                 server: srv ? srv.querySelector('.v').innerText.trim() : null,
                 button: btn ? { text: btn.innerText.trim(), disabled: btn.disabled,
                                 aria_busy: btn.getAttribute('aria-busy') } : null,
                 result: res ? res.innerText.replace(/\\s+/g, ' ').trim() : null }; }""", cid)


def open_clusters(page) -> None:
    page.goto(BASE + "/#page=clusters", wait_until="networkidle")
    page.wait_for_selector("#cc-head", timeout=30_000)
    page.wait_for_selector("[data-cc-cluster]", timeout=30_000)
    page.wait_for_timeout(1000)


def no_api_error(page, where: str) -> None:
    n = page.locator("text=Dashboard API error").count()
    expect(f"no 'Dashboard API error' ({where})", n == 0, n)


def refresh_and_wait(page, cid: str) -> dict:
    page.click(f"#cc-refresh-{cid}")
    page.wait_for_function("(cid) => { const r = document.getElementById('cc-refresh-result-' + cid);"
                           " return r && !/probing/.test(r.innerText); }", arg=cid, timeout=60_000)
    return card_facts(page, cid)


def walk_width(ctx, width: int, height: int, n: int, api_requests: list) -> int:
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("response", lambda r: api_requests.append((time.time(), r.status))
            if r.url.split("?")[0].endswith("/api/clusterconfigs") and r.request.method == "GET" else None)
    page.set_viewport_size({"width": width, "height": height})
    open_clusters(page)
    w = f"{width}"
    say(f"[{w}] whoami", whoami(page))
    say(f"[{w}] page scrollWidth / innerWidth",
        page.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]"))
    overflow = page.evaluate("() => document.documentElement.scrollWidth > window.innerWidth")
    expect(f"[{w}] no sideways page scroll", not overflow, overflow)
    no_api_error(page, f"{w} open")

    # --- #314: the banner, the chip and hint on the sharing entries, no chip on disabled entries at that URL ---
    api = page.evaluate("async () => (await fetch('/api/clusterconfigs', { credentials: 'same-origin' })).json()")
    warnings = api.get("warnings") or []
    say(f"[{w}] api warnings", warnings)
    banners = page.evaluate("() => [...document.querySelectorAll('[data-cc-warning]')]"
                            ".map(b => b.innerText.replace(/\\s+/g, ' ').trim())")
    say(f"[{w}] banner text", banners)
    expect(f"[{w}] banner names shared-qa, shared-rnd and https://api.crc.testing:6443",
           len(banners) == 1 and all(s in banners[0] for s in ("shared-qa", "shared-rnd", "https://api.crc.testing:6443"))
           and banners[0].startswith("⚠️"), banners)
    rows = [{"id": c["id"], "enabled": c["enabled"], "retired": c["retired"], "api_url": c["api_url"],
             "source": c["source"], "credential": c["credential"], "status": c["status"]} for c in api["clusters"]]
    if n == 1:
        (EVIDENCE / "api-clusterconfigs.json").write_text(json.dumps(
            {"fetched_at": utc(), "as": USER, "warnings": warnings, "clusters": rows}, indent=2) + "\n")
        say("wrote", "evidence/api-clusterconfigs.json")
    same_url = [r for r in rows if r["api_url"].rstrip("/") == "https://api.crc.testing:6443"]
    say(f"[{w}] entries at https://api.crc.testing:6443",
        [f"{r['id']}:{'enabled' if r['enabled'] else 'disabled'}{':retired' if r['retired'] else ''}" for r in same_url])
    for cid in ("shared-qa", "shared-rnd"):
        f = card_facts(page, cid)
        say(f"[{w}] {cid} card", f)
        other = "shared-rnd" if cid == "shared-qa" else "shared-qa"
        expect(f"[{w}] {cid}: chip and hint naming {other}", bool(f and f["chip"] and f["hint"]
               and f"Also declared by {other}" in f["hint"]), f and [f["chip"], f["hint"]])
    head = page.locator("#cc-head"); shot(head, f"{n:02d}-{w}-banner.png"); n += 1
    for cid in ("shared-qa", "shared-rnd"):
        shot(card(page, cid), f"{n:02d}-{w}-{cid}-chip.png"); n += 1
    disabled = sorted(r["id"] for r in same_url if not r["enabled"])
    chips = {cid: (card_facts(page, cid) or {}).get("chip") for cid in disabled}
    say(f"[{w}] disabled entries at the shared URL ({len(disabled)}), chip shown", chips)
    expect(f"[{w}] no chip on any disabled entry at the shared URL", not any(chips.values()) and len(disabled) >= 3,
           {"disabled": len(disabled), "with chip": sum(1 for v in chips.values() if v)})
    for cid in disabled[:3]:
        shot(card(page, cid), f"{n:02d}-{w}-disabled-{cid}.png"); n += 1

    # --- #311: Refresh on shared-rnd ---
    idle = card_facts(page, REFRESHED)
    say(f"[{w}] {REFRESHED} idle", idle)
    expect(f"[{w}] idle button reads Refresh, enabled, no result line",
           idle["button"] == {"text": "Refresh", "disabled": False, "aria_busy": None} and idle["result"] is None, idle)
    shot(card(page, REFRESHED), f"{n:02d}-{w}-refresh-idle.png"); n += 1

    cdp = ctx.new_cdp_session(page)
    cdp.send("Network.enable")
    cdp.send("Network.emulateNetworkConditions",
             {"offline": False, "latency": 4000, "downloadThroughput": -1, "uploadThroughput": -1})
    t_click = utc()
    page.click(f"#cc-refresh-{REFRESHED}")
    page.wait_for_timeout(600)
    flight = card_facts(page, REFRESHED)
    say(f"[{w}] {REFRESHED} in flight (clicked {t_click})", flight)
    expect(f"[{w}] in flight: Refreshing…, disabled, aria-busy, probing line",
           flight["button"] == {"text": "Refreshing…", "disabled": True, "aria_busy": "true"}
           and (flight["result"] or "").startswith("Refresh: probing /version and users/~"), flight)
    shot(card(page, REFRESHED), f"{n:02d}-{w}-refresh-in-flight.png"); n += 1
    cdp.send("Network.emulateNetworkConditions",
             {"offline": False, "latency": 0, "downloadThroughput": -1, "uploadThroughput": -1})
    page.wait_for_function("(cid) => { const r = document.getElementById('cc-refresh-result-' + cid);"
                           " return r && !/probing/.test(r.innerText); }", arg=REFRESHED, timeout=60_000)
    done = card_facts(page, REFRESHED)
    say(f"[{w}] {REFRESHED} answered", done)
    ok = bool(re.match(r"^Refresh: connected · \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|\+00:00)", done["result"] or ""))
    expect(f"[{w}] succeeded: 'connected · <ISO-8601 UTC>', button back to Refresh",
           ok and done["button"]["text"] == "Refresh" and not done["button"]["disabled"], done["result"])
    shot(card(page, REFRESHED), f"{n:02d}-{w}-refresh-succeeded.png"); n += 1

    # The repaint replaces #main's nodes: a marker set on the result line now is gone after a repaint, while
    # the line (kept in view.clusterRefresh) is drawn again. Waiting 65 s crosses one 60-second timer tick.
    page.evaluate("(cid) => { document.getElementById('cc-refresh-result-' + cid).dataset.walkMark = 'before'; }",
                  REFRESHED)
    before_n, t0 = len(api_requests), time.time()
    say(f"[{w}] waiting 65 s for the repaint", "from " + utc())
    page.wait_for_timeout(65_000)
    after = card_facts(page, REFRESHED)
    marked = page.evaluate("(cid) => document.getElementById('cc-refresh-result-' + cid).dataset.walkMark || null",
                           REFRESHED)
    polls = [s for (t, s) in api_requests[before_n:] if t >= t0]
    say(f"[{w}] after 65 s: GET /api/clusterconfigs during the wait", polls)
    say(f"[{w}] after 65 s: result line node marker (null = the node was repainted)", marked)
    say(f"[{w}] {REFRESHED} after the repaint", after)
    expect(f"[{w}] after the 60 s repaint: the same answer still shown on a repainted node",
           after["result"] == done["result"] and marked is None and len(polls) >= 1,
           {"same": after["result"] == done["result"], "repainted": marked is None, "polls": len(polls)})
    shot(card(page, REFRESHED), f"{n:02d}-{w}-refresh-after-repaint.png"); n += 1

    # --- a refused Refresh, only if the lab really has one ---
    for cid in MOCKS:
        f = card_facts(page, cid)
        if not f or not f["button"]:
            say(f"[{w}] {cid}", "no Refresh button on this card" if f else "no card")
            continue
        r = refresh_and_wait(page, cid)
        say(f"[{w}] {cid} refresh answered", r["result"])
        shot(card(page, cid), f"{n:02d}-{w}-refresh-{cid}.png"); n += 1
    no_api_error(page, f"{w} end")
    expect(f"[{w}] no uncaught page errors", not errors, errors)
    page.close()
    return n


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "walk"
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        login(page)
        who = whoami(page)
        say("whoami", who)
        status = page.evaluate("async () => { const s = {}; for (const u of ['/api/whoami', '/api/clusterconfigs'])"
                               " s[u] = (await fetch(u, { credentials: 'same-origin' })).status; return s; }")
        say("status", status)
        if mode == "after":
            tabs = page.evaluate("() => [...document.querySelectorAll('button.tab')].map(b => b.textContent.trim())")
            has = any("Cluster Configurations" in t for t in tabs)
            say("has Cluster Configurations tab", has)
            expect("after the grant's removal: no cluster-admin tier, the tab absent, /api/clusterconfigs 403",
                   who["cluster_admin"] is False and not has and status["/api/clusterconfigs"] == 403,
                   {"cluster_admin": who["cluster_admin"], "tab": has, "status": status["/api/clusterconfigs"]})
        else:
            expect("developer holds the cluster-admin tier for the walk",
                   who["cluster_admin"] is True and status["/api/clusterconfigs"] == 200, who)
            page.close()
            n, api_requests = 1, []
            for width, height in WIDTHS:
                n = walk_width(ctx, width, height, n, api_requests)
        br.close()
    say("failures", failures)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
