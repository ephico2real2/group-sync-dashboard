#!/usr/bin/env python3
"""Targeted validation of the 2026-09-23 release on the DEPLOYED dashboard, beside the e2e walk.

The walk proves every tab renders; this proves what the release changed:
  #320  the walk's own browser login is captured from the oauth-server AUDIT LOG (the default source)
  #261  the Namespace audit page: the reconciling clause (#326), the cluster-wide card and worklist drills
        (#327), the reach tile and disclosure (#328), the scope note and name separators (#329), and the
        risk tint on even rows plus index-row focus ids (#330)

Reuses the walk's own login and step recording (local-development/e2e-walk/e2e_capture.py), so a failed
check is a recorded FAIL with a screenshot, never a pretty picture of a broken page. The password comes from
GSD_UI_PASSWORD only. Exit 0 only when every check passed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(os.environ["E2E_WALK_DIR"])))
from e2e_capture import Walk, api_json, login, now  # noqa: E402
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright  # noqa: E402

ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
EVERY_GRANT_TOGGLE = "button[data-ns-grants]"   # index.html#function nsAuditPage: the one control that opens Every grant


def instant(stamp: str | None) -> dt.datetime | None:
    """A store stamp (`%Y-%m-%dT%H:%M:%S.%fZ`, gsd/auditlog.py#STAMP) or the walk's own (`…SZ`) as a datetime."""
    if not isinstance(stamp, str) or not ISO.match(stamp):
        return None
    return dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def form_login_row(row: dict, login_at: str) -> bool:
    """Is this row THIS run's form login? An audit-log row of kind=credential (the POST /login the form makes;
    the oauth-proxy's re-authorisation right after it is kind=session, which the first version of this check
    accepted — measured 2026-09-23) whose own instant `at` — the oauth-server's stamp of the request — is at or
    after the moment the walk started logging in. Only `at` is compared: the row also carries `observed_at`, the
    poller's clock when it first read the line, and a backfill (a fresh store, a rotated file) observes OLD
    logins after login_at, so a check that took any ISO-8601 field on the row accepted a login this run did not
    make (review of #335, OB1-lite NA-1). Both clocks are UTC."""
    if row.get("source") != "audit-log" or row.get("kind") != "credential":
        return False
    at, since = instant(row.get("at")), instant(login_at)
    return at is not None and since is not None and at >= since


def worklist(page):
    return page.locator("section.card", has=page.locator("h3:text-is('Exposure by namespace')"))


def open_nsaudit(w: Walk) -> None:
    w.page.click('button.tab:text-is("Namespace audit")')
    w.page.wait_for_selector("h3:text-is('Exposure by namespace')", timeout=20_000)
    w.page.wait_for_load_state("networkidle")
    w.page.wait_for_timeout(600)


def check_login_captured(w: Walk, login_at: str, user: str, timeout_s: int) -> None:
    """#320: the login this run just made through the route must appear as an audit-log row."""
    clusters = [c["id"] for c in (api_json(w, "/api/clusters").get("json") or []) if c.get("id")]
    deadline = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=timeout_s)
    found, last = None, {}
    while dt.datetime.now(dt.timezone.utc) < deadline and not found:
        for cid in clusters:
            res = api_json(w, f"/api/clusters/{cid}/logins?user={user}&kind=all&limit=20")
            body = res.get("json") or {}
            last[cid] = {"status": res.get("status"), "attempts": (body.get("attempts") or [])[:3]}
            for row in body.get("attempts") or []:
                if form_login_row(row, login_at):
                    found = {"cluster": cid, "row": row}
                    break
            if found:
                break
        if not found:
            w.page.wait_for_timeout(15_000)
    w.record("#320 the route's form login is captured from the audit log as a credential row", found is not None,
             json.dumps(found, default=str)[:600] if found else
             f"no audit-log credential row for {user} at or after {login_at} within {timeout_s}s", api=found or last)


def expand_every_grant(page) -> bool:
    """Open Every grant through its own control and say whether the section is open afterwards. Its rows are
    in the DOM either way — the section is a `hidden` div — and a hidden row still has a computed background
    (measured in Chromium, review of #335, OB1-lite NA-2), so a check that counted rows without this answer
    could not tell an open section from one that never opened."""
    toggle = page.locator(EVERY_GRANT_TOGGLE)
    if toggle.count() != 1:
        return False
    if toggle.get_attribute("aria-expanded") != "true":
        toggle.click()
    try:
        page.wait_for_function("() => { const s = document.getElementById('every-grant'); return !!s && !s.hidden; }",
                               timeout=5_000)
    except PlaywrightTimeoutError:
        return False
    return True


def check_even_row_tint(page) -> tuple[bool, str]:
    """#330: a Critical or High row keeps its tint on an even row. "Even" is per tbody — the scope of the CSS's
    nth-child (`[...tb.children]` indexes the same element siblings) — and only rendered rows count (the first
    version of this check counted across every table on the page, hidden rows included; measured 2026-09-23)."""
    expanded = expand_every_grant(page)
    tints = page.evaluate("""() => [...document.querySelectorAll('.audit-table tbody')].flatMap((tb, t) =>
        [...tb.children].map((tr, i) => ({ table: t, nth: i + 1, cls: tr.className,
            rendered: tr.getClientRects().length > 0,
            bg: tr.querySelector('td') ? getComputedStyle(tr.querySelector('td')).backgroundColor : null })))""")
    rendered = [t for t in tints if t["rendered"]]
    strong_even = [t for t in rendered if t["nth"] % 2 == 0 and re.search(r"risk-(critical|high)\b", t["cls"])]
    if not expanded:
        return False, f"Every grant did not open through its control ({len(tints)} rows, {len(rendered)} rendered)"
    if strong_even:
        ok = all(t["bg"] not in ("rgba(0, 0, 0, 0)", "transparent") for t in strong_even)
        return ok, f"Every grant open; even Critical/High rows: {strong_even[:4]}"
    return True, (f"Every grant open; no Critical/High row falls on an even row of its table here "
                  f"({len(rendered)} rendered rows) — nothing to paint")


def check_nsaudit(w: Walk) -> None:
    page = w.page
    open_nsaudit(w)
    w.errors.clear()
    state = page.evaluate("""() => ({
        scope: data.userBindings && data.userBindings.scope,
        platformWithFindings: data.namespaces && data.namespaces.platform_with_findings,
        rollup: ((data.userBindings || {}).by_namespace || []).map((r) => r.namespace),
        hiddenWithFindings: ((data.namespaces || {}).namespaces || []).filter((n) => n.platform && n.direct_grants).map((n) => n.name),
    })""")
    shot = w.shot("nsaudit-top")

    # #327: the cluster scope is its own card, above the worklist; the worklist ranks namespaces only
    headings = [" ".join(h.split()) for h in page.locator("#main section.card h3").all_inner_texts()]
    wide_idx = [i for i, h in enumerate(headings) if h.startswith("Cluster-wide direct grants")]
    ok = bool(wide_idx) and headings[wide_idx[0] + 1] == "Exposure by namespace" \
        and "CLUSTER-WIDE" not in worklist(page).inner_text()
    w.record("#327 the cluster-wide card sits above the worklist, which ranks namespaces only", ok,
             f"card headings: {headings}", shot)

    # #327: every worklist namespace is a drill; the first opens its page
    drills = worklist(page).locator("tbody button.drill[data-ns]")
    names = drills.evaluate_all("els => els.map(e => e.dataset.ns)")
    rows = worklist(page).locator("tbody tr").count()
    ok = rows > 0 and len(names) == rows
    if ok:
        first = names[0]
        drills.first.click()
        page.wait_for_selector(f"h2:has-text('{first}')", timeout=15_000)
        shot = w.shot("nsaudit-worklist-drill")
        ok = page.evaluate("() => location.hash").endswith(f"ns={first}")
        page.go_back()
        page.wait_for_selector("h3:text-is('Exposure by namespace')", timeout=15_000)
        page.wait_for_timeout(500)
    else:
        shot = None
    w.record("#327 each worklist namespace opens its page", ok, f"{len(names)} drills for {rows} rows: {names[:6]}", shot)

    # #326: the reconciling clause names only hidden namespaces the worklist holds
    line_loc = page.locator("#ns-show-platform").locator("xpath=..")
    line = " ".join(line_loc.inner_text().split()) if line_loc.count() else ""
    expected = [n for n in state["hiddenWithFindings"] if n in state["rollup"]]
    if state["platformWithFindings"] and expected:
        ok = "This hides rows, never findings:" in line and expected[0] in line \
            and "still ranked in Exposure by namespace above" in line
    else:
        ok = "never findings" not in line
    line_loc.scroll_into_view_if_needed() if line_loc.count() else None
    w.record("#326 the platform line names a hidden namespace that still holds a finding", ok,
             f"platform_with_findings={state['platformWithFindings']}, hidden-with-findings held by the worklist={expected}; "
             f"line: {line[:300]}", w.shot("nsaudit-platform-line", full=False), api=state)

    # #329: names in "Who is exposed" are separated in the text a reader copies
    cells = worklist(page).locator("td.who").all()
    multi = [c for c in cells if c.locator(".who-name").count() >= 2]
    if multi:
        text = multi[0].evaluate("el => el.textContent")
        ok = " · " in text
        detail = f"textContent: {text.strip()[:160]}"
    else:
        ok, detail = True, "no worklist row names two or more people on this cluster — nothing to separate"
    w.record("#329 exposed names are separated in the copied text", ok, detail)

    # #330: a Critical or High row keeps its tint on an even row (check_even_row_tint above)
    ok, detail = check_even_row_tint(page)
    w.record("#330 the risk tint is painted on even rows", ok, detail)

    # #330: an index row's drill carries an id, so focus survives the 60 s repaint
    ids = page.evaluate("() => [...document.querySelectorAll('tr.rowlink[data-ns] button.drill')].map((b) => b.id).slice(0, 5)")
    w.record("#330 index-row drills carry ids for focus restore", bool(ids) and all(i.startswith("ns-row-") for i in ids),
             f"first ids: {ids}")

    # #329: the scope note shows while the bar's box holds a query, and goes with Escape
    box = page.locator("#f-ns-search")
    before = worklist(page).locator("tbody tr").count()
    box.fill(names[0][:4] if names else "a")
    page.wait_for_timeout(700)
    shown = "Find namespace in the bar narrows the Namespaces list below, not this table" in " ".join(worklist(page).inner_text().split())
    same_rows = worklist(page).locator("tbody tr").count() == before
    shot = w.shot("nsaudit-scope-note", full=False)
    box.press("Escape")
    page.wait_for_timeout(500)
    gone = "Find namespace in the bar" not in worklist(page).inner_text()
    w.record("#329 the worklist states the bar's box does not narrow it", shown and same_rows and gone,
             f"note shown={shown}, worklist rows unchanged={same_rows}, cleared by Escape={gone}", shot)

    # #328: a namespace page's cluster-wide reach is a tile, a split and a disclosure
    target = names[0] if names else None
    if target:
        page.locator(f"tbody button.drill[data-ns='{target}']").first.click()
        page.wait_for_selector(f"h2:has-text('{target}')", timeout=15_000)
        page.wait_for_timeout(600)
        tile = page.locator(".kpi", has_text="Reached cluster-wide")
        toggle = page.locator("#ns-wide-toggle")
        value = tile.locator(".value").first.inner_text().strip() if tile.count() else None
        detail = f"tile={tile.count()} reading {value!r}, toggle={toggle.count()}"
        ok = tile.count() == 1
        if toggle.count():
            before_state = toggle.get_attribute("aria-expanded")
            toggle.click()
            page.wait_for_timeout(400)
            after = page.locator("#ns-wide-toggle").get_attribute("aria-expanded")
            listed = page.locator("#ns-wide-list:not([hidden]) tbody tr").count()
            ok = ok and before_state == "false" and after == "true" and listed > 0
            detail += f", aria-expanded {before_state}→{after}, subjects listed={listed}"
        shot = w.shot("nsaudit-namespace-reach")
        w.record("#328 the namespace page shows the reach tile and its disclosure", ok and w.page_clean() is None,
                 f"{target}: {detail}", shot)
    problem = w.page_clean()
    w.record("no JavaScript error and no API error across the checks", problem is None, problem or "clean")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--login-user", required=True)
    ap.add_argument("--provider", default="developer")
    ap.add_argument("--out", required=True)
    ap.add_argument("--capture-timeout", type=int, default=300)
    args = ap.parse_args()
    password = os.environ.get("GSD_UI_PASSWORD")
    if not password:
        print("GSD_UI_PASSWORD is required", file=sys.stderr)
        return 2
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 900}, ignore_https_errors=True)
        page = context.new_page()
        w = Walk(page, out)
        started = now()
        login_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        if login(w, args.base, args.login_user, password, args.provider):
            ver = api_json(w, "/api/version")
            w.record("GET /api/version", ver.get("status") == 200, f"HTTP {ver.get('status')}", api=ver.get("json"))
            check_nsaudit(w)
            check_login_captured(w, login_at, args.login_user, args.capture_timeout)
        browser.close()
    summary = {"started": started, "finished": now(), "base": args.base, "login_user": args.login_user,
               "login_at": login_at, "steps": w.steps,
               "passed": sum(1 for s in w.steps if s["ok"]), "failed": sum(1 for s in w.steps if not s["ok"])}
    (out / "results_release.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    print(f"\n{summary['passed']} checks passed, {summary['failed']} failed → {out}")
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
