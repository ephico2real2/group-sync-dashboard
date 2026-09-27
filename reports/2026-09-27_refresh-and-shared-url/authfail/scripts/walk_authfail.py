#!/usr/bin/env python3
"""The addendum: #311's `auth_failed` branch, on a throwaway cluster Secret whose bearer token no server issued.

    walk_authfail.py walk   the ⚠️ banner at 1280 px while walk-authfail is live (three entries share the URL), its
                            card before any press, then Refresh on walk-authfail at 1280, 768 and 375 px. Expected at
                            each width: `auth_failed` and the Rejoin hint. It stops at the first other answer.
    walk_authfail.py gone   after the Secret's deletion and discovery's retirement: the banner at 1280 px naming
                            shared-qa and shared-rnd only, and the walk-authfail card retired

Logs in as `developer` through the parent walk's `login` (../../scripts/walk.py); the password comes from the
environment only (GSD_UI_PASSWORD). Screenshots go to ../screenshots, numbered from 40 after the parent walk's 39."""
import importlib.util, pathlib, re, sys
sys.dont_write_bytecode = True   # the parent walk is imported by path; leave no __pycache__ in the report folder
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("parent_walk", HERE.parents[1] / "scripts" / "walk.py")
pw = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(pw)
SHOTS = HERE.parent / "screenshots"
CID = "walk-authfail"
URL = "https://api.crc.testing:6443"
HINT = "Next step: Rejoin (#316), not built yet"


def shot(el, name: str) -> None:
    el.scroll_into_view_if_needed(); el.page.wait_for_timeout(300)
    el.screenshot(path=str(SHOTS / name))
    pw.say("shot", name)


def banners(page) -> list[str]:
    return page.evaluate("() => [...document.querySelectorAll('[data-cc-warning]')]"
                         ".map(b => b.innerText.replace(/\\s+/g, ' ').trim())")


def api_row(page) -> dict | None:
    api = page.evaluate("async () => (await fetch('/api/clusterconfigs', { credentials: 'same-origin' })).json()")
    pw.say("api warnings", api.get("warnings") or [])
    row = next((c for c in api["clusters"] if c["id"] == CID), None)
    pw.say(f"api {CID} row", row and {k: row[k] for k in ("id", "enabled", "retired", "api_url", "source",
                                                         "credential", "status", "error")})
    return row


def walk(page, errors: list) -> None:
    pw.open_clusters(page)
    row = api_row(page)
    b = banners(page)
    pw.say("banner text", b)
    pw.expect("banner names shared-qa, shared-rnd and walk-authfail at " + URL,
              len(b) == 1 and all(s in b[0] for s in ("shared-qa", "shared-rnd", CID, URL)), b)
    shot(page.locator("#cc-head"), "40-1280-banner-three.png")
    before = pw.card_facts(page, CID)
    pw.say(f"{CID} card before Refresh", before)
    pw.expect(f"{CID} is live, with the chip and a Refresh button",
              bool(row and row["enabled"] and not row["retired"] and before and before["chip"] and before["button"]),
              before)
    shot(pw.card(page, CID), "41-1280-walk-authfail-before.png")
    n = 42
    for width, height in pw.WIDTHS:
        page.set_viewport_size({"width": width, "height": height})
        pw.open_clusters(page)
        facts = pw.refresh_and_wait(page, CID)
        hint = page.evaluate("(cid) => { const h = document.querySelector('#cc-refresh-result-' + cid + ' .cc-hint');"
                             " return h ? h.innerText.trim() : null; }", CID)
        pw.say(f"[{width}] {CID} refresh answered", facts["result"])
        pw.say(f"[{width}] {CID} Rejoin hint", hint)
        ok = bool(re.match(r"^Refresh: auth_failed · \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", facts["result"] or "")
                  and hint and HINT in hint)
        pw.expect(f"[{width}] {CID}: auth_failed with the Rejoin hint", ok, facts["result"])
        shot(pw.card(page, CID), f"{n:02d}-{width}-walk-authfail-refused.png"); n += 1
        if not ok:
            pw.say("stopped", "the answer was not auth_failed with the Rejoin hint; no further press")
            break
    pw.no_api_error(page, "end")
    pw.expect("no uncaught page errors", not errors, errors)


def gone(page, errors: list) -> None:
    pw.open_clusters(page)
    row = api_row(page)
    b = banners(page)
    pw.say("banner text", b)
    pw.expect("banner names shared-qa and shared-rnd only",
              len(b) == 1 and all(s in b[0] for s in ("shared-qa", "shared-rnd", URL)) and CID not in b[0], b)
    shot(page.locator("#cc-head"), "45-1280-banner-two.png")
    facts = pw.card_facts(page, CID)
    pw.say(f"{CID} card after the deletion", facts)
    pw.expect(f"{CID} retired: disabled, no chip, no Refresh",
              bool(row and row["retired"] and not row["enabled"] and facts and not facts["chip"]
                   and facts["button"] is None), facts)
    if facts:
        shot(pw.card(page, CID), "46-1280-walk-authfail-retired.png")
    pw.no_api_error(page, "gone")
    pw.expect("no uncaught page errors", not errors, errors)


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "walk"
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 900})
        page = ctx.new_page(); errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        pw.login(page)
        who = pw.whoami(page)
        pw.say("whoami", who)
        pw.expect("developer holds the cluster-admin tier", who["cluster_admin"] is True, who)
        (gone if mode == "gone" else walk)(page, errors)
        br.close()
    pw.say("failures", pw.failures)
    sys.exit(1 if pw.failures else 0)


if __name__ == "__main__":
    main()
