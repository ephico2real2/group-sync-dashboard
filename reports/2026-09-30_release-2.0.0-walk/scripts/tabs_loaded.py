#!/usr/bin/env python3
"""The two cluster-admin tabs, captured once their content has painted, as `developer` at 1440 px (the e2e walk's
viewport). The first run's e2e pass photographed KPIs and Cluster Configurations while each still read `Loading…`:
`walk_tabs` in local-development/e2e-walk/e2e_capture.py waits for any `h2`, and the loading card has one. This pass
waits for `Loading…` to leave `#main` and for the dim (`stale`) to clear, and records how long that took from the
tab's click.

Reads only: after the login, a route guard aborts every request to the dashboard's API that is not a GET. The
password comes from GSD_UI_PASSWORD only; the fleet mask and clean() are epicd.py's."""
import json, sys, time
from playwright.sync_api import sync_playwright

from epicd import FLEET_RE, FLEET_ROW, MASK_LOG, SHOTS, expect, failures, login, say, whoami, write

blocked: list[str] = []


def guard(route) -> None:
    if route.request.method == "GET":
        route.continue_()
    else:
        blocked.append(f"{route.request.method} {route.request.url.split('?')[0]}")
        route.abort()


def capture(page, label: str, name: str) -> dict:
    t0 = time.monotonic()
    page.click(f'button.tab:text-is("{label}")')
    page.wait_for_selector(f'button.tab[aria-current="page"]:text-is("{label}")', timeout=15_000)
    page.wait_for_function("() => { const m = document.getElementById('main');"
                           " return !m.classList.contains('stale') && !/Loading…/.test(m.innerText); }", timeout=60_000)
    painted = round(time.monotonic() - t0, 1)
    page.wait_for_timeout(500)
    head = page.locator("#main h2").first.inner_text().strip()
    row, named = page.locator(FLEET_ROW), page.get_by_text(FLEET_RE)
    with MASK_LOG.open("a") as f:
        f.write(json.dumps({"shot": f"screenshots/{name}", "fleet_row_elements": row.count(),
                            "elements_naming_the_account": named.count(),
                            "page_text_named_the_account": bool(FLEET_RE.search(page.locator("body").inner_text()))}) + "\n")
    page.mouse.move(0, 0)
    page.screenshot(path=str(SHOTS / name), full_page=True, mask=[row, named])
    say("shot", f"screenshots/{name}")
    return {"tab": label, "seconds_from_click_to_painted": painted, "heading": head,
            "h2s": [h.strip() for h in page.locator("#main h2").all_inner_texts()][:12]}


def main() -> None:
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(ignore_https_errors=True, viewport={"width": 1440, "height": 900}, color_scheme="dark")
        page = ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        try:
            login(page)
            page.route("**/api/**", guard)          # after the login, whose form is a POST to the OAuth server
            who = whoami(page)
            say("whoami", who)
            expect("developer holds the cluster-admin tier", who["cluster_admin"] is True, who)
            got = [capture(page, "KPIs", "11-1440-tab-kpis-painted.png"),
                   capture(page, "Cluster Configurations", "12-1440-tab-cluster-configurations-painted.png")]
            write("tabs-painted.json", {"whoami": who, "tabs": got})
            for g in got:
                expect(f"{g['tab']} painted past `Loading…`", bool(g["heading"]), g)
            expect("no 'Dashboard API error'", page.locator("text=Dashboard API error").count() == 0, None)
            expect("no uncaught page errors", not errors, errors)
            expect("no request other than GET was attempted", not blocked, blocked)
        except Exception as e:  # noqa: BLE001
            failures.append(f"exception: {type(e).__name__}")
            say("STOPPED on an exception", f"{type(e).__name__}: {e}")
        br.close()
    say("tabs_loaded failures", failures)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
