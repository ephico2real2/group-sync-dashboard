#!/usr/bin/env python3
"""#404 on the deployed Cluster Configurations tab, as `developer`, once gsd-cluster-gitops-404 exists.

At 1280, 768 and 375 px: the header's `by source` chips and its discovery line, and the gitops-404 card's source chip,
credential hint and footer, with whether it offers Rotate or Delete. Nothing is pressed: a route guard aborts every
request to /api/clusterconfigs that is not a GET, and the walk fails if one is attempted.

The password comes from the environment only (GSD_UI_PASSWORD); the fleet account's name from GSD_FLEET_ACCOUNT, used
only to mask it in the screenshots and never printed. Screenshots go to ../screenshots. Exits non-zero on an uncaught
page error, a visible "Dashboard API error", a blocked write, or a failed expectation."""
import json, os, pathlib, re, sys, time
from playwright.sync_api import sync_playwright

BASE = os.environ.get("GSD_BASE", "https://group-sync-dashboard.apps-crc.testing")
USER = "developer"
HERE = pathlib.Path(__file__).resolve().parent
SHOTS = HERE.parent / "screenshots"
WIDTHS = [(1280, 900), (768, 1024), (375, 812)]
CLUSTER, MAP, SECRET = "gitops-404", "cluster-onboarding-404", "gsd-cluster-gitops-404"
CHIP = f"ConfigMap {MAP} → Secret {SECRET}"
FLEET = os.environ["GSD_FLEET_ACCOUNT"]
failures: list[str] = []
blocked: list[str] = []


def utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def say(tag: str, value) -> None:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    print(f"{utc()} {tag:34s}: {text.replace(FLEET, '<fleet account>')}", flush=True)


def expect(what: str, ok: bool, detail) -> None:
    say(f"{'PASS' if ok else 'FAIL'} {what}", detail)
    if not ok:
        failures.append(what)


def guard(route) -> None:
    """Reads pass; every other request to the cluster-configuration API is aborted and recorded."""
    req = route.request
    if req.method == "GET":
        route.continue_()
    else:
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


def shot(page, el, name: str) -> None:
    """The element alone, with every element that shows the fleet account's name painted over in grey."""
    el.scroll_into_view_if_needed(); page.wait_for_timeout(300)
    el.screenshot(path=str(SHOTS / name), mask=[page.get_by_text(FLEET)], mask_color="#8a8a8a")
    say("shot", name)


def header_facts(page) -> dict:
    return page.evaluate("""() => { const h = document.getElementById('cc-head');
        const kv = (k) => { const r = [...h.querySelectorAll('.cc-kv')].find(x => x.querySelector('.k').textContent === k);
                            return r ? r.querySelector('.v').innerText.replace(/\\s+/g, ' ').trim() : null; };
        return { count: h.querySelector('h2 .rp-count').innerText.trim(), by_source: kv('by source'),
                 configmap_selector: kv('ConfigMap selector'), discovery: kv('discovery'),
                 configmap_cards: [...document.querySelectorAll('[data-cc-cluster] h2 .cc-src-configmap')]
                                   .map(c => [c.closest('[data-cc-cluster]').dataset.ccCluster, c.innerText.trim()]) }; }""")


def card_facts(page) -> dict | None:
    return page.evaluate("""(cid) => { const c = document.getElementById('cc-cluster-' + cid);
        if (!c) return null;
        const t = (sel) => { const e = c.querySelector(sel); return e ? e.innerText.replace(/\\s+/g, ' ').trim() : null; };
        const kv = (k) => { const r = [...c.querySelectorAll('.cc-kv')].find(x => x.querySelector('.k').textContent === k);
                            return r ? r.querySelector('.v').innerText.replace(/\\s+/g, ' ').trim() : null; };
        return { chip: t('h2 .cc-src-configmap'), heading: t('h2'), credential: kv('credential'), server: kv('server'),
                 connection: kv('connection'), foot: t('.cc-foot'),
                 rotate: c.querySelectorAll('[data-cc-rotate]').length, delete: c.querySelectorAll('[data-cc-delete]').length,
                 buttons: [...c.querySelectorAll('button')].map(b => b.innerText.trim()) }; }""", CLUSTER)


def walk_width(ctx, width: int, height: int, n: int) -> int:
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.set_viewport_size({"width": width, "height": height})
    page.goto(BASE + "/#page=clusters", wait_until="networkidle")
    page.wait_for_selector("#cc-head", timeout=30_000)
    page.wait_for_selector(f"#cc-cluster-{CLUSTER}", timeout=30_000)
    page.wait_for_timeout(1000)
    w = f"{width}"
    sw = page.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")
    expect(f"[{w}] no sideways page scroll (scrollWidth, innerWidth)", sw[0] <= sw[1], sw)

    head = header_facts(page)
    say(f"[{w}] header", head)
    expect(f"[{w}] by source counts the map's cluster: ConfigMap 1", bool(re.search(r"\bConfigMap 1\b", head["by_source"] or "")),
           head["by_source"])
    expect(f"[{w}] the only ConfigMap-sourced card is {CLUSTER}, with its chip", head["configmap_cards"] == [[CLUSTER, CHIP]],
           head["configmap_cards"])
    say(f"[{w}] discovery line (#467)", head["discovery"])
    shot(page, page.locator("#cc-head"), f"{n:02d}-{w}-header.png"); n += 1

    card = card_facts(page)
    say(f"[{w}] {CLUSTER} card", card)
    expect(f"[{w}] the chip reads `{CHIP}`", card is not None and card["chip"] == CHIP, card and card["chip"])
    expect(f"[{w}] no Rotate and no Delete on the generated row", card is not None and card["rotate"] == 0
           and card["delete"] == 0, card and {"rotate": card["rotate"], "delete": card["delete"], "buttons": card["buttons"]})
    shot(page, page.locator(f"#cc-cluster-{CLUSTER}"), f"{n:02d}-{w}-card-{CLUSTER}.png"); n += 1

    api_errors = page.locator("text=Dashboard API error").count()
    expect(f"[{w}] no 'Dashboard API error'", api_errors == 0, api_errors)
    expect(f"[{w}] no uncaught page errors", not errors, errors)
    page.close()
    return n


def main() -> None:
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 900})
        ctx.route(re.compile(r".*/api/clusterconfigs.*"), guard)
        page = ctx.new_page()
        login(page)
        who = page.evaluate("() => ({ user: data.whoami.user, cluster_admin: (data.whoami.visibility || {}).cluster_admin })")
        status = page.evaluate("async () => (await fetch('/api/clusterconfigs', { credentials: 'same-origin' })).status")
        say("whoami", who)
        expect("developer holds the cluster-admin tier for the walk", who["cluster_admin"] is True and status == 200,
               {**who, "/api/clusterconfigs": status})
        page.close()
        if not failures:
            n = 1
            for width, height in WIDTHS:
                n = walk_width(ctx, width, height, n)
        br.close()
    expect("no write request was attempted (the route guard blocked none)", not blocked, blocked)
    say("failures", failures)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
