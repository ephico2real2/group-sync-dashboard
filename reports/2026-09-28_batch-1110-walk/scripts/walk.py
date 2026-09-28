#!/usr/bin/env python3
"""#390, #404, #441 (and the search #447 needs) on the deployed Cluster Configurations tab, as `developer`.

    walk.py walk    at 1280, 768 and 375 px:
                    #404  the header's `by source` chips and discovery line, and any ConfigMap-sourced card's chip;
                    #390  Rotate opened on mock-trusted, a throwaway string typed, the page left alone until the
                          60-second timer has repainted #main, the field's value read through the DOM (its length
                          and whether it equals what was typed; the field stays type=password in every capture),
                          then closed and reopened empty. Overwrite is never pressed: a route guard aborts any
                          write request and the walk fails if one is attempted;
                    #441  Refresh on shared-rnd (and, at 1280, on the three mocks, to find a card that offers
                          Rejoin); a page-wide duplicate-id check with the cc-refresh_ / cc-refresh-result_ ids
                          listed, and the result's own card named;
                    #435  /api/clusters and /api/clusterconfigs as served now, for the poll-status comparison.
    walk.py after   a fresh login once the walk's grant is removed: the tier the dashboard now answers.

shared-qa's card is never clicked. The password comes from the environment only (GSD_UI_PASSWORD); nothing here
prints or stores it. Screenshots go to ../screenshots, API answers (selected fields) to ../evidence. Exits
non-zero on an uncaught page error, a visible "Dashboard API error", a blocked write, or a failed expectation."""
import json, os, pathlib, re, sys, time
from playwright.sync_api import sync_playwright

BASE = os.environ.get("GSD_BASE", "https://group-sync-dashboard.apps-crc.testing")
USER = "developer"
HERE = pathlib.Path(__file__).resolve().parent
SHOTS = HERE.parent / "screenshots"
EVIDENCE = HERE.parent / "evidence"
WIDTHS = [(1280, 900), (768, 1024), (375, 812)]
ROTATE_CARD = "mock-trusted"
DRAFT = "walk-draft-not-a-token"          # not a credential for anything; typed into a type=password field
REFRESHED = "shared-rnd"
MOCKS = ["mock-privateca", "mock-selfsigned", "mock-trusted"]
NEVER = {"shared-qa"}                     # the operator's rule: its card is never clicked
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
    """Reads and Refresh pass; every other request to the cluster-configuration API is aborted and recorded."""
    req = route.request
    path = req.url.split("?")[0]
    if req.method == "GET" or (req.method == "POST" and path.endswith("/refresh")
                               and not any(f"/{n}/" in path for n in NEVER)):
        route.continue_()
    else:
        blocked.append(f"{req.method} {path}")
        say("BLOCKED", f"{req.method} {path}")
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


def shot(el, name: str) -> None:
    el.scroll_into_view_if_needed(); el.page.wait_for_timeout(300)
    el.screenshot(path=str(SHOTS / name))
    say("shot", name)


def card(page, cid: str):
    return page.locator(f"#cc-cluster-{cid}")


def open_clusters(page) -> None:
    page.goto(BASE + "/#page=clusters", wait_until="networkidle")
    page.wait_for_selector("#cc-head", timeout=30_000)
    page.wait_for_selector("[data-cc-cluster]", timeout=30_000)
    page.wait_for_timeout(1000)


def no_api_error(page, where: str) -> None:
    n = page.locator("text=Dashboard API error").count()
    expect(f"no 'Dashboard API error' ({where})", n == 0, n)


def header_facts(page) -> dict:
    return page.evaluate("""() => { const h = document.getElementById('cc-head');
        const kv = (k) => { const r = [...h.querySelectorAll('.cc-kv')].find(x => x.querySelector('.k').textContent === k);
                            return r ? r.querySelector('.v').innerText.replace(/\\s+/g, ' ').trim() : null; };
        return { count: h.querySelector('h2 .rp-count').innerText.trim(), by_source: kv('by source'),
                 configmap_selector: kv('ConfigMap selector'), discovery: kv('discovery'),
                 configmap_cards: [...document.querySelectorAll('[data-cc-cluster] h2 .cc-src-configmap')]
                                   .map(c => [c.closest('[data-cc-cluster]').dataset.ccCluster, c.innerText.trim()]) }; }""")


def rotate_facts(page, cid: str) -> dict | None:
    """The field's facts, never its value: whether it equals the typed draft, its length, its type."""
    return page.evaluate("""([cid, draft]) => { const f = document.getElementById('cc-rotate-token-' + cid);
        if (!f) return null;
        return { equals_draft: f.value === draft, length: f.value.length, type: f.type,
                 marker: f.dataset.walkMark || null, focused: document.activeElement === f }; }""", [cid, DRAFT])


def id_check(page) -> dict:
    return page.evaluate("""() => { const ids = [...document.querySelectorAll('[id]')].map(e => e.id);
        const seen = new Set(), dup = new Set();
        ids.forEach(i => { if (seen.has(i)) dup.add(i); seen.add(i); });
        const owner = (i) => { const e = document.getElementById(i), c = e && e.closest('[data-cc-cluster]');
                               return c ? c.dataset.ccCluster : null; };
        const pick = (p) => ids.filter(i => i.startsWith(p)).map(i => [i, owner(i)]);
        return { ids: ids.length, duplicates: [...dup],
                 refresh_buttons: pick('cc-refresh_'), refresh_results: pick('cc-refresh-result_') }; }""")


def refresh_line(page, cid: str) -> str | None:
    return page.evaluate("(cid) => { const r = document.getElementById('cc-refresh-result_' + cid);"
                         " return r ? r.innerText.replace(/\\s+/g, ' ').trim() : null; }", cid)


def press_refresh(page, cid: str) -> str:
    assert cid not in NEVER
    page.click(f"#cc-refresh_{cid}")
    page.wait_for_function("(cid) => { const r = document.getElementById('cc-refresh-result_' + cid);"
                           " return r && !/probing/.test(r.innerText); }", arg=cid, timeout=60_000)
    return refresh_line(page, cid)


def walk_rotate(page, w: str, n: int, api_requests: list) -> int:
    """#390: the draft survives the minute's repaint, and closing the panel drops it."""
    link = page.locator(f"#cc-rotate-{ROTATE_CARD}")
    expect(f"[{w}] {ROTATE_CARD} offers Rotate (a Secret-sourced card, writes on)", link.count() == 1, link.count())
    if not link.count():
        return n
    link.click()
    field = page.locator(f"#cc-rotate-token-{ROTATE_CARD}")
    field.wait_for(timeout=10_000)
    expect(f"[{w}] the panel opens empty", rotate_facts(page, ROTATE_CARD)["length"] == 0,
           rotate_facts(page, ROTATE_CARD))
    field.fill(DRAFT)
    typed = rotate_facts(page, ROTATE_CARD)
    say(f"[{w}] typed", typed)
    expect(f"[{w}] typed: {len(DRAFT)} characters in a type=password field",
           typed["equals_draft"] and typed["length"] == len(DRAFT) and typed["type"] == "password", typed)
    shot(card(page, ROTATE_CARD), f"{n:02d}-{w}-rotate-typed.png"); n += 1
    # A marker on the field's node: a repaint of #main replaces the node, so the marker's absence proves it.
    page.evaluate("(cid) => { document.getElementById('cc-rotate-token-' + cid).dataset.walkMark = 'before'; }",
                  ROTATE_CARD)
    before_n, t0 = len(api_requests), time.time()
    say(f"[{w}] leaving the page alone", "from " + utc())
    waited = 0
    for _ in range(3):   # the timer skips the repaint when the payload is unchanged: up to three ticks
        page.wait_for_timeout(65_000); waited += 65
        after = rotate_facts(page, ROTATE_CARD)
        if after is None or after["marker"] is None:
            break
    polls = [s for (t, s) in api_requests[before_n:] if t >= t0]
    say(f"[{w}] after {waited} s: GET /api/clusterconfigs", polls)
    say(f"[{w}] after {waited} s: the field", after)
    expect(f"[{w}] after the repaint: the field is a new node holding the draft ({len(DRAFT)} chars), still masked",
           bool(after) and after["marker"] is None and after["equals_draft"] and after["length"] == len(DRAFT)
           and after["type"] == "password" and len(polls) >= 1,
           {"repainted": bool(after) and after["marker"] is None, "equals_draft": bool(after) and after["equals_draft"],
            "length": after and after["length"], "type": after and after["type"], "polls": polls, "waited_s": waited})
    shot(card(page, ROTATE_CARD), f"{n:02d}-{w}-rotate-after-repaint.png"); n += 1
    link.click()                                   # close: the draft belongs to the open panel
    page.wait_for_timeout(300)
    closed = rotate_facts(page, ROTATE_CARD)
    expect(f"[{w}] closed: no field", closed is None, closed)
    link.click()                                   # reopen
    field.wait_for(timeout=10_000)
    reopened = rotate_facts(page, ROTATE_CARD)
    expect(f"[{w}] reopened: the field is empty", reopened["length"] == 0 and not reopened["equals_draft"], reopened)
    shot(card(page, ROTATE_CARD), f"{n:02d}-{w}-rotate-reopened-empty.png"); n += 1
    link.click()                                   # close again, empty
    page.wait_for_timeout(300)
    expect(f"[{w}] left closed", rotate_facts(page, ROTATE_CARD) is None, None)
    return n


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
    sw = page.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")
    expect(f"[{w}] no sideways page scroll (scrollWidth, innerWidth)", sw[0] <= sw[1], sw)
    no_api_error(page, f"{w} open")

    # --- #404: the header's counts, as the lab has them ---
    head = header_facts(page)
    say(f"[{w}] header", head)
    shot(page.locator("#cc-head"), f"{n:02d}-{w}-header.png"); n += 1

    # --- #390: Rotate's draft across the repaint ---
    n = walk_rotate(page, w, n, api_requests)

    # --- #441: Refresh on shared-rnd lands on its own card; no two elements share an id ---
    line = press_refresh(page, REFRESHED)
    say(f"[{w}] {REFRESHED} refresh answered", line)
    ids = id_check(page)
    say(f"[{w}] id check", ids)
    own = dict(ids["refresh_results"]).get(f"cc-refresh-result_{REFRESHED}")
    expect(f"[{w}] no duplicate id on the page; the result is on {REFRESHED}'s card",
           not ids["duplicates"] and own == REFRESHED and bool(re.match(r"^Refresh: connected · ", line or "")),
           {"duplicates": ids["duplicates"], "result on": own, "line": line})
    shot(card(page, REFRESHED), f"{n:02d}-{w}-refresh-{REFRESHED}.png"); n += 1

    if width == 1280:
        # --- #447's precondition: a card that offers Rejoin after its Refresh (never shared-qa) ---
        answers = {}
        for cid in MOCKS:
            if page.locator(f"#cc-refresh_{cid}").count():
                answers[cid] = press_refresh(page, cid)
        say(f"[{w}] mock refresh answers", answers)
        ids = id_check(page)
        say(f"[{w}] id check after 4 Refresh answers", ids)
        mismatched = [i for i, owner in ids["refresh_buttons"] + ids["refresh_results"] if i.split("_", 1)[1] != owner]
        expect(f"[{w}] after 4 answers: no duplicate id; every cc-refresh id sits on its own card",
               not ids["duplicates"] and not mismatched and len(ids["refresh_results"]) == 1 + len(answers),
               {"duplicates": ids["duplicates"], "mismatched": mismatched, "results": len(ids["refresh_results"])})
        offers = page.evaluate("() => [...document.querySelectorAll('[data-cc-rejoin]')].map(b => b.dataset.ccRejoin)")
        say(f"[{w}] cards offering Rejoin (#447 needs one)", offers)
        for cid in MOCKS:
            if cid in answers:
                shot(card(page, cid), f"{n:02d}-{w}-refresh-{cid}.png"); n += 1

        # --- #435: the poll status each cluster is served with now ---
        polls = page.evaluate("""async () => {
            const r = await fetch('/api/clusters', { credentials: 'same-origin' });
            const cl = r.ok ? await r.json() : [];
            const cc = await (await fetch('/api/clusterconfigs', { credentials: 'same-origin' })).json();
            return { api_clusters_status: r.status,
                     clusters: cl.filter(c => c.enabled !== false).map(c => ({ id: c.id, status: c.status,
                         reachable: c.reachable, last_poll: c.last_poll, error: c.error || null })),
                     clusterconfigs: cc.clusters.filter(c => c.enabled && !c.retired).map(c => ({ id: c.id,
                         source: c.source, status: c.status, last_poll: c.last_poll, error: c.error || null,
                         rejoinable: c.rejoinable })) }; }""")
        (EVIDENCE / "walk-api-polls.json").write_text(json.dumps({"fetched_at": utc(), "as": USER, **polls},
                                                                 indent=2) + "\n")
        say("wrote", "evidence/walk-api-polls.json")
        say(f"[{w}] served poll status", {c["id"]: c["status"] for c in polls["clusterconfigs"]})

    no_api_error(page, f"{w} end")
    expect(f"[{w}] no uncaught page errors", not errors, errors)
    page.close()
    return n


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "walk"
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 900})
        ctx.route(re.compile(r".*/api/clusterconfigs.*"), guard)
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
            if not failures:
                n, api_requests = 1, []
                for width, height in WIDTHS:
                    n = walk_width(ctx, width, height, n, api_requests)
        br.close()
    expect("no write request was attempted (the route guard blocked none)", not blocked, blocked)
    say("failures", failures)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
