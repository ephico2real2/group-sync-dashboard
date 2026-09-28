#!/usr/bin/env python3
"""#447 on the deployed Cluster Configurations tab, as `developer`, on the throwaway entry `walk-447`.

    walk_447.py walk   at 1280, 768 and 375 px: Refresh on walk-447 answers auth_failed and the card offers Rejoin;
                       Rejoin is opened, `developer-walk` and a password that lies inside it typed,
                       and Rejoin pressed. The dialog must read `HTTP 422 — rejoin-password-within-username: …`, the
                       password field must be empty, and the card's Rejoin line must say the same. Cancel then clears
                       the dialog.

A route guard lets reads through, and only two writes: POST …/walk-447/refresh and POST …/walk-447/rejoin, the latter
only with exactly the body this walk types. Everything else is aborted and fails the walk. No other card is clicked.
The login password comes from the environment only (GSD_UI_PASSWORD) and is never printed; the typed Rejoin values
are never printed either, only compared. Exits non-zero on a page error, a blocked request or a failed expectation."""
import json, os, pathlib, re, sys, time
from playwright.sync_api import sync_playwright

BASE = os.environ.get("GSD_BASE", "https://group-sync-dashboard.apps-crc.testing")
USER = "developer"
HERE = pathlib.Path(__file__).resolve().parent
SHOTS = HERE.parent / "screenshots"
WIDTHS = [(1280, 900), (768, 1024), (375, 812)]
ENTRY = "walk-447"
REJOIN_USER = "developer-walk"            # no such account; the password below lies inside it
REJOIN_PASSWORD = os.environ["GSD_WALK_REJOIN_PASSWORD"]   # any part of REJOIN_USER, e.g. `walk`; given at run time
SENTENCE = ("HTTP 422 — rejoin-password-within-username: the password must not be the username or a part of it, "
            "ignoring case and surrounding spaces; it was not sent")
failures: list[str] = []
blocked: list[str] = []
rejoin_statuses: list[int] = []


def utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def say(tag: str, value) -> None:
    print(f"{utc()} {tag:34s}: {value if isinstance(value, str) else json.dumps(value)}", flush=True)


def expect(what: str, ok: bool, detail) -> None:
    say(f"{'PASS' if ok else 'FAIL'} {what}", detail)
    if not ok:
        failures.append(what)


def guard(route) -> None:
    req = route.request
    path = req.url.split("?")[0]
    if req.method == "GET" or (req.method == "POST" and path.endswith(f"/api/clusterconfigs/{ENTRY}/refresh")):
        route.continue_()
        return
    if req.method == "POST" and path.endswith(f"/api/clusterconfigs/{ENTRY}/rejoin"):
        try:
            body = json.loads(req.post_data or "")
        except ValueError:
            body = None
        if body == {"username": REJOIN_USER, "password": REJOIN_PASSWORD}:
            route.continue_()
            return
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


def shot(el, name: str) -> None:
    el.scroll_into_view_if_needed(); el.page.wait_for_timeout(300)
    el.screenshot(path=str(SHOTS / name))
    say("shot", name)


def open_clusters(page) -> None:
    page.goto(BASE + "/#page=clusters", wait_until="networkidle")
    page.wait_for_selector("#cc-head", timeout=30_000)
    page.wait_for_selector("[data-cc-cluster]", timeout=30_000)
    page.wait_for_timeout(1000)


def text(page, sel: str) -> str | None:
    return page.evaluate("(s) => { const e = document.querySelector(s);"
                         " return e ? e.innerText.replace(/\\s+/g, ' ').trim() : null; }", sel)


def dialog_facts(page) -> dict:
    return page.evaluate("""() => { const d = document.getElementById('rejoin-dialog');
        const u = document.getElementById('rejoin-username'), p = document.getElementById('rejoin-password');
        return { open: d.open, cluster: d.dataset.cluster || null, msg: document.getElementById('rejoin-msg').innerText.trim(),
                 username_is_typed: u.value === %s, username_length: u.value.length,
                 password_length: p.value.length, password_type: p.type }; }""" % json.dumps(REJOIN_USER))


def walk_width(ctx, width: int, height: int, n: int) -> int:
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("response", lambda r: rejoin_statuses.append(r.status)
            if r.request.method == "POST" and r.url.split("?")[0].endswith(f"/{ENTRY}/rejoin") else None)
    page.set_viewport_size({"width": width, "height": height})
    open_clusters(page)
    w = f"{width}"
    card = page.locator(f"#cc-cluster-{ENTRY}")
    expect(f"[{w}] the {ENTRY} card is listed", card.count() == 1, card.count())
    if not card.count():
        page.close(); return n
    say(f"[{w}] {ENTRY} heading", text(page, f"#cc-cluster-{ENTRY} h2"))
    expect(f"[{w}] no Rejoin before Refresh", page.locator(f"#cc-rejoin-{ENTRY}").count() == 0, None)

    # Refresh: the stored bogus token is refused, and the card offers Rejoin
    page.click(f"#cc-refresh_{ENTRY}")
    page.wait_for_function("(id) => { const r = document.getElementById('cc-refresh-result_' + id);"
                           " return r && !/probing/.test(r.innerText); }", arg=ENTRY, timeout=60_000)
    line = text(page, f"#cc-refresh-result_{ENTRY}")
    say(f"[{w}] refresh answered", line)
    offer = page.locator(f"#cc-rejoin-{ENTRY}")
    expect(f"[{w}] Refresh answers auth_failed and the card offers Rejoin",
           bool(re.match(r"^Refresh: auth_failed · ", line or "")) and offer.count() == 1
           and (offer.inner_text().strip() if offer.count() else "") == "Rejoin…",
           {"line": line, "rejoin_button": offer.inner_text().strip() if offer.count() else None})
    shot(card, f"{n:02d}-{w}-447-refused-rejoin-offered.png"); n += 1
    if not offer.count():
        page.close(); return n

    # Rejoin: type, press, read
    offer.click()
    page.wait_for_function("() => document.getElementById('rejoin-dialog').open", timeout=10_000)
    page.fill("#rejoin-username", REJOIN_USER)
    page.fill("#rejoin-password", REJOIN_PASSWORD)
    typed = dialog_facts(page)
    say(f"[{w}] dialog typed", typed)
    expect(f"[{w}] the dialog is open on {ENTRY}, the password masked",
           typed["open"] and typed["cluster"] == ENTRY and typed["password_type"] == "password"
           and typed["password_length"] == len(REJOIN_PASSWORD), typed)
    before = len(rejoin_statuses)
    page.click("#rejoin-go")
    page.wait_for_function("() => /^HTTP |^[a-z]/.test(document.getElementById('rejoin-msg').innerText)"
                           " && !/^Signing in/.test(document.getElementById('rejoin-msg').innerText)", timeout=30_000)
    answered = dialog_facts(page)
    card_line = text(page, f"#cc-rejoin-result-{ENTRY}")
    say(f"[{w}] dialog answered", answered)
    say(f"[{w}] card Rejoin line", card_line)
    say(f"[{w}] rejoin POST statuses", rejoin_statuses[before:])
    expect(f"[{w}] the dialog reads the exact 422 sentence, the password field is empty",
           answered["msg"] == SENTENCE and answered["password_length"] == 0 and answered["open"],
           {"msg_is_sentence": answered["msg"] == SENTENCE, "password_length": answered["password_length"]})
    expect(f"[{w}] the card's Rejoin line reads the same", card_line == f"Rejoin: {SENTENCE}", card_line)
    expect(f"[{w}] one POST …/rejoin, answered 422", rejoin_statuses[before:] == [422], rejoin_statuses[before:])
    shot(page.locator("#rejoin-dialog"), f"{n:02d}-{w}-447-dialog-422.png"); n += 1
    page.click("#rejoin-cancel")
    page.wait_for_function("() => !document.getElementById('rejoin-dialog').open", timeout=10_000)
    closed = dialog_facts(page)
    expect(f"[{w}] Cancel closes the dialog and clears both fields",
           not closed["open"] and closed["username_length"] == 0 and closed["password_length"] == 0, closed)
    shot(card, f"{n:02d}-{w}-447-card-rejoin-line.png"); n += 1

    sw = page.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")
    expect(f"[{w}] no sideways page scroll (scrollWidth, innerWidth)", sw[0] <= sw[1], sw)
    expect(f"[{w}] no 'Dashboard API error'", page.locator("text=Dashboard API error").count() == 0, None)
    expect(f"[{w}] no uncaught page errors", not errors, errors)
    page.close()
    return n


def main() -> None:
    if sys.argv[1:] != ["walk"]:
        sys.exit("usage: walk_447.py walk")
    n = int(os.environ.get("GSD_SHOT_START", "19"))
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 900})
        ctx.route(re.compile(r".*/api/clusterconfigs.*"), guard)
        page = ctx.new_page()
        login(page)
        who = page.evaluate("() => ({ user: data.whoami.user, cluster_admin: (data.whoami.visibility || {}).cluster_admin })")
        say("whoami", who)
        expect("developer holds the cluster-admin tier", who["cluster_admin"] is True, who)
        if not failures:
            page.close()
            for width, height in WIDTHS:
                n = walk_width(ctx, width, height, n)
        br.close()
    expect("the route guard blocked no request", not blocked, blocked)
    say("rejoin POST statuses, all", rejoin_statuses)
    say("failures", failures)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
