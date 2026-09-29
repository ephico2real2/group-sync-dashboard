#!/usr/bin/env python3
"""How long a hash edit takes to repaint, for a real position as well as an unknown cluster id (why the second pass
waits for the repaint). As `developer`, with walk.py's login and route guard: after a Home load, set `location.hash`
and read view.page, #main's first h2 and the header's `updated` stamp at 1, 3 and 6 s. Reads only."""
import json, re, sys, time
import walk
from playwright.sync_api import sync_playwright

FACTS = """() => ({ hash: location.hash, view_page: view.page, view_cluster: view.cluster,
    main_h2: (document.querySelector('#main h2') || {}).textContent || null,
    main_stale: document.getElementById('main').classList.contains('stale'),
    updated: document.getElementById('last-refresh').textContent })"""

with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 900})
    ctx.route(re.compile(r"^" + re.escape(walk.BASE) + r"/api/.*"), walk.guard)
    page = ctx.new_page(); errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    walk.login(page)
    for target in ("#page=groups", "#page=overview&cluster=dashboard", "#page=overview&cluster=zzz-unknown"):
        page.goto(walk.BASE + "/", wait_until="networkidle"); page.wait_for_timeout(2000)
        walk.say("home", page.evaluate(FACTS))
        page.evaluate("(h) => { location.hash = h; }", target)
        t0 = time.time()
        for at in (1, 3, 6):
            page.wait_for_timeout(max(0, int((t0 + at - time.time()) * 1000)))
            walk.say(f"{target} +{at}s", page.evaluate(FACTS))
    walk.say("page errors", errors)
    walk.say("blocked", walk.blocked)
    br.close()
