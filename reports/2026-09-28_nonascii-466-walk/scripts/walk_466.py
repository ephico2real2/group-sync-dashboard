#!/usr/bin/env python3
"""#466 on the deployed dashboard, as `developer`, read-only.

    walk_466.py api <label>   log in, then write evidence/<label>-api.json: /api/clusters and /api/clusterconfigs as
                              served now — each enabled cluster's poll status, the discovery instant, and every
                              finding. The fleet section of /api/clusterconfigs is not written (it names the fleet
                              account).
    walk_466.py walk          at 1280, 768 and 375 px: the Cluster Configurations tab's Findings card lists
                              `gsd-cluster-walk-466` with code `ca-data-invalid` and the exact detail; every
                              enabled cluster's card is still on the tab; the Findings card is captured.
    walk_466.py after         a fresh login once the grant is removed: the tier the dashboard now answers.

Only GET requests reach the dashboard: a route guard over /api/* aborts every other method and fails the walk. No
card is clicked. The password comes from the environment only (GSD_UI_PASSWORD) and is never printed. Exits non-zero
on an uncaught page error, a visible "Dashboard API error", a blocked request or a failed expectation."""
import json, os, pathlib, re, sys, time
from playwright.sync_api import sync_playwright

BASE = os.environ.get("GSD_BASE", "https://group-sync-dashboard.apps-crc.testing")
USER = "developer"
HERE = pathlib.Path(__file__).resolve().parent
SHOTS = HERE.parent / "screenshots"
EVIDENCE = HERE.parent / "evidence"
WIDTHS = [(1280, 900), (768, 1024), (375, 812)]
SECRET = "gsd-cluster-walk-466"
CODE = "ca-data-invalid"
DETAIL = "tlsClientConfig.caData does not decode to a PEM bundle that loads: TypeError"
failures: list[str] = []
blocked: list[str] = []


def utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def say(tag: str, value) -> None:
    print(f"{utc()} {tag:34s}: {value if isinstance(value, str) else json.dumps(value)}", flush=True)


def expect(what: str, ok: bool, detail) -> None:
    say(f"{'PASS' if ok else 'FAIL'} {what}", detail)
    if not ok:
        failures.append(what)


def guard(route) -> None:
    """Reads pass; any other request to the dashboard's API is aborted and recorded."""
    req = route.request
    if req.method in ("GET", "HEAD"):
        route.continue_()
        return
    blocked.append(f"{req.method} {req.url.split('?')[0]}")
    say("BLOCKED", blocked[-1])
    route.abort()


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


def served(page) -> dict:
    """The two APIs as served now, selected fields only (no fleet section, no credential)."""
    got = page.evaluate("""async () => {
        const get = async (u) => { const r = await fetch(u, { credentials: 'same-origin' });
                                   return [r.status, r.ok ? await r.json() : null]; };
        const [s1, cl] = await get('/api/clusters');
        const [s2, cc] = await get('/api/clusterconfigs');
        return {
          api_clusters_status: s1, api_clusterconfigs_status: s2,
          clusters: (cl || []).filter(c => c.enabled !== false).map(c => ({ id: c.id, status: c.status,
              reachable: c.reachable, last_poll: c.last_poll, error: c.error || null })),
          discovery: cc ? { namespace: cc.secrets.namespace, label: cc.secrets.label,
                            last_discovery: cc.secrets.last_discovery, error: cc.secrets.error } : null,
          clusterconfigs: cc ? cc.clusters.filter(c => c.enabled && !c.retired).map(c => ({ id: c.id,
              source: c.source, status: c.status, last_poll: c.last_poll, error: c.error || null })) : null,
          findings: cc ? cc.findings : null }; }""")
    text = re.sub(r"sha256~[A-Za-z0-9_-]+", "sha256~<redacted>", json.dumps(got))
    return json.loads(text)


def open_clusters(page) -> None:
    page.goto(BASE + "/#page=clusters", wait_until="networkidle")
    page.wait_for_selector("#cc-head", timeout=30_000)
    page.wait_for_selector("#cc-findings", timeout=30_000)
    page.wait_for_timeout(1000)


def findings_on_page(page) -> list[dict]:
    return page.evaluate("""() => [...document.querySelectorAll('#cc-findings .cc-finding')].map(a => {
        const kv = (k) => { const r = [...a.querySelectorAll('.cc-kv')].find(x => x.querySelector('.k').textContent === k);
                            return r ? r.querySelector('.v').innerText.replace(/\\s+/g, ' ').trim() : null; };
        return { source: kv('source'), code: kv('code'), detail: kv('detail') }; })""")


def walk_width(ctx, width: int, height: int, n: int, expected_cards: list[str]) -> int:
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.set_viewport_size({"width": width, "height": height})
    open_clusters(page)
    w = f"{width}"
    found = findings_on_page(page)
    say(f"[{w}] findings on the tab", found)
    mine = [f for f in found if f["source"] == SECRET]
    expect(f"[{w}] one finding for {SECRET}: code {CODE}, the exact detail",
           mine == [{"source": SECRET, "code": CODE, "detail": DETAIL}], mine)
    cards = page.evaluate("() => [...document.querySelectorAll('[data-cc-cluster]')].map(c => c.dataset.ccCluster)")
    missing = [c for c in expected_cards if c not in cards]
    expect(f"[{w}] every enabled cluster still has its card", not missing, {"missing": missing, "cards": len(cards)})
    expect(f"[{w}] no card for walk-466 (it was refused, never loaded)", "walk-466" not in cards, None)
    el = page.locator("#cc-findings")
    el.scroll_into_view_if_needed(); page.wait_for_timeout(300)
    name = f"{n:02d}-{w}-findings-walk-466.png"
    el.screenshot(path=str(SHOTS / name)); say("shot", name); n += 1
    sw = page.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")
    expect(f"[{w}] no sideways page scroll (scrollWidth, innerWidth)", sw[0] <= sw[1], sw)
    expect(f"[{w}] no 'Dashboard API error'", page.locator("text=Dashboard API error").count() == 0, None)
    expect(f"[{w}] no uncaught page errors", not errors, errors)
    page.close()
    return n


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in ("api", "walk", "after") or (mode == "api" and len(sys.argv) != 3):
        sys.exit("usage: walk_466.py api <label> | walk | after")
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 900})
        ctx.route(re.compile(r".*/api/.*"), guard)
        page = ctx.new_page()
        login(page)
        who = whoami(page)
        say("whoami", who)
        got = served(page)
        say("status", {"/api/clusters": got["api_clusters_status"],
                       "/api/clusterconfigs": got["api_clusterconfigs_status"]})
        if mode == "after":
            tabs = page.evaluate("() => [...document.querySelectorAll('button.tab')].map(b => b.textContent.trim())")
            has = any("Cluster Configurations" in t for t in tabs)
            say("has Cluster Configurations tab", has)
            expect("after the grant's removal: no cluster-admin tier, the tab absent, /api/clusterconfigs 403",
                   who["cluster_admin"] is False and not has and got["api_clusterconfigs_status"] == 403,
                   {"cluster_admin": who["cluster_admin"], "tab": has, "status": got["api_clusterconfigs_status"]})
        else:
            expect("developer holds the cluster-admin tier",
                   who["cluster_admin"] is True and got["api_clusterconfigs_status"] == 200, who)
            if mode == "api":
                out = EVIDENCE / f"{sys.argv[2]}-api.json"
                out.write_text(json.dumps({"fetched_at": utc(), "as": USER, **got}, indent=2) + "\n")
                say("wrote", str(out.relative_to(HERE.parent)))
                say("served poll status", {c["id"]: c["status"] for c in got["clusterconfigs"] or []})
                say("findings", got["findings"])
            elif not failures:
                page.close()
                expected_cards = [c["id"] for c in got["clusterconfigs"]]
                n = int(os.environ.get("GSD_SHOT_START", "1"))
                for width, height in WIDTHS:
                    n = walk_width(ctx, width, height, n, expected_cards)
        br.close()
    expect("the route guard blocked no request", not blocked, blocked)
    say("failures", failures)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
