#!/usr/bin/env python3
"""PROOF 2 — #285's fleet-account row on the deployed Cluster Configurations tab, as `developer` with the walk's
temporary grant (after reports/2026-09-30_release-2.0.0-walk/scripts/epicd.py). SPEC_S4c §3.10 defines the row:
`fleet account <username> · last confirmed <instant> · last ping <target>: <outcome>` (or `not yet confirmed by the
daily ping`), with a `suspended` badge while the account's Lease holds an entry.

What it does, at 1280 px and then at 375 px:
  - reads `GET /api/clusterconfigs` with the page's own fetch and keeps only its `fleet` object, the username replaced
    by `<fleet account>` (evidence/api-clusterconfigs-fleet.json);
  - reads every `[data-cc-fleet]` row's text, its badges, and whether the page scrolls sideways
    (evidence/fleet-rows-<width>.json, cleaned the same way);
  - photographs the `#cc-head` card and the fleet row alone with the account's name masked: the name's span, every
    element whose text names it, and an opaque box over each rendered occurrence (TEXT_BOXES_JS, as
    reports/2026-09-30_release-2.0.0-walk/scripts/e2e_masked.py does); evidence/mask-log.jsonl has the counts;
  - once, at 1280 px, the same row UNMASKED into GSD_WALK_TMP (outside the repo): the OCR check's positive control.

A route guard aborts every request to /api/ that is not a GET, so nothing on the tab can be pressed into a write.
The UI password comes from GSD_UI_PASSWORD only and is never printed; the fleet account's name is read from its Lease
with oc into a variable and never printed. Exits non-zero on an uncaught page error, a visible "Dashboard API error",
a blocked write, or a failed expectation."""
import json, os, pathlib, re, subprocess, sys, time
from playwright.sync_api import sync_playwright

BASE = os.environ.get("GSD_BASE", "https://group-sync-dashboard.apps-crc.testing")
USER = "developer"
NS = "group-sync-dashboard"
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
SHOTS = ROOT / "screenshots"
EV = ROOT / "evidence"
TMP = pathlib.Path(os.environ["GSD_WALK_TMP"])
MASK_LOG = EV / "mask-log.jsonl"
# The username span only: `.v > .mono` alone also matches the `last confirmed` instant's span (ccFleetRows in
# local-development/gsd/static/index.html), and run 1 masked the instant with it (evidence/run1/mask-log.jsonl: 2).
FLEET_ROW = "[data-cc-fleet] .v > .mono:first-child"
CLEAN_ENV = {k: v for k, v in os.environ.items() if k != "GSD_UI_PASSWORD"}
failures: list[str] = []
blocked: list[str] = []

FLEET = json.loads(subprocess.run(
    ["oc", "get", "leases.coordination.k8s.io", "-n", NS, "-l", "groupsync-dashboard.io/lease-type=fleet-account",
     "-o", "json"], env=CLEAN_ENV, capture_output=True, text=True, check=True, timeout=60).stdout)["items"][0][
    "metadata"]["annotations"]["groupsync-dashboard.io/account"]
FLEET_RE = re.compile(re.escape(FLEET), re.I)

# One opaque box over every rendered occurrence of the name, from the glyphs' own client rects (e2e_masked.py).
TEXT_BOXES_JS = """(needle) => {
  const boxes = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = node.data.toLowerCase();
    for (let at = text.indexOf(needle); at !== -1; at = text.indexOf(needle, at + needle.length)) {
      const range = document.createRange();
      range.setStart(node, at);
      range.setEnd(node, at + needle.length);
      for (const r of range.getClientRects()) {
        if (r.width === 0 || r.height === 0) continue;
        const box = document.createElement('div');
        box.dataset.walkMask = '';
        box.style.cssText = `position:absolute;left:${r.left + scrollX - 2}px;top:${r.top + scrollY - 2}px;` +
          `width:${r.width + 4}px;height:${r.height + 4}px;background:#ff00ff;z-index:2147483647;pointer-events:none`;
        boxes.push(box);
      }
    }
  }
  boxes.forEach((b) => document.body.appendChild(b));
  return boxes.length;
}"""


def clean(text: str) -> str:
    text = re.sub(r"sha256~[A-Za-z0-9_-]+", "sha256~<redacted>", text)
    return FLEET_RE.sub("<fleet account>", text)


def utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def say(tag: str, value) -> None:
    text = value if isinstance(value, str) else json.dumps(value)
    print(clean(f"{utc()} {tag:62s}: {text}"), flush=True)


def write(name: str, value) -> None:
    (EV / name).write_text(clean(json.dumps(value, indent=2) + "\n"))
    say("wrote", f"evidence/{name}")


def expect(what: str, ok: bool, detail) -> None:
    say(f"{'PASS' if ok else 'FAIL'} {what}", detail)
    if not ok:
        failures.append(what)


def guard(route) -> None:
    """GETs pass; any other method to /api/ is aborted and recorded."""
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


def open_clusters(page) -> None:
    page.goto(BASE + "/#page=clusters", wait_until="networkidle")
    page.wait_for_selector("#cc-head", timeout=30_000)
    page.wait_for_function("() => !document.getElementById('main').classList.contains('stale')", timeout=30_000)
    page.wait_for_timeout(800)


def rows(page) -> list[dict]:
    """Each fleet row's text as rendered, and its badges' text and class."""
    return page.evaluate("""() => [...document.querySelectorAll('[data-cc-fleet]')].map((r) => ({
        // the label by textContent: `.cc-kv .k` is `text-transform: uppercase` (app.css), so innerText says FLEET ACCOUNT
        text: ((r.querySelector('.k') || {}).textContent || '').trim() + ' ' + (r.querySelector('.v') || r).innerText.replace(/\\s+/g, ' ').trim(),
        inner_text: r.innerText.replace(/\\s+/g, ' ').trim(),
        badges: [...r.querySelectorAll('.badge')].map((b) => ({ text: b.innerText.trim(), class: b.className })) }))""")


def shot(page, selector: str, path: pathlib.Path, masked: bool = True) -> None:
    el = page.locator(selector).first
    el.scroll_into_view_if_needed(); page.mouse.move(0, 0); page.wait_for_timeout(300)
    if not masked:
        el.screenshot(path=str(path))
        say("control (unmasked, outside the repo)", path.name)
        return
    row, named = page.locator(FLEET_ROW), page.get_by_text(FLEET_RE)
    try:
        boxes = page.evaluate(TEXT_BOXES_JS, FLEET.lower())
        with MASK_LOG.open("a") as f:
            f.write(json.dumps({"shot": f"screenshots/{path.name}", "fleet_row_elements": row.count(),
                                "elements_naming_the_account": named.count(), "text_boxes": boxes,
                                "page_text_named_the_account": bool(FLEET_RE.search(page.locator("body").inner_text()))})
                    + "\n")
        el.screenshot(path=str(path), mask=[row, named, page.locator("[data-walk-mask]")])
    finally:
        page.evaluate("() => document.querySelectorAll('[data-walk-mask]').forEach((b) => b.remove())")
    say("shot", f"screenshots/{path.name}")


def width_of(page) -> dict:
    return page.evaluate("() => ({ innerWidth: window.innerWidth, scrollWidth: document.documentElement.scrollWidth })")


SHAPE = re.compile(r"^fleet account <fleet account> · (last confirmed \d{4}-\d\d-\d\d \d\d:\d\d"
                   r"|not yet confirmed by the daily ping)( · last ping \S+: \S+)?( suspended)?$")


def at_width(page, px: int, api_fleet: dict) -> None:
    open_clusters(page)
    expect(f"{px}: no 'Dashboard API error'", page.locator("text=Dashboard API error").count() == 0, None)
    got, w = rows(page), width_of(page)
    write(f"fleet-rows-{px}.json", {"read_at": utc(), "rows": got, "page": w})
    accounts = api_fleet.get("accounts") or []
    expect(f"{px}: one row per fleet account in the API", len(got) == len(accounts),
           {"rows": len(got), "accounts": len(accounts)})
    for r in got:
        expect(f"{px}: the row has SPEC_S4c §3.10's shape", bool(SHAPE.match(clean(r["text"]))), clean(r["text"]))
    for r, a in zip(got, accounts):
        expect(f"{px}: `suspended` badge painted iff the Lease holds an entry",
               any(b["text"] == "suspended" for b in r["badges"]) == bool(a.get("suspended")),
               {"badges": r["badges"], "suspended_entries": len(a.get("suspended") or [])})
        if a.get("last_ok"):   # fmtStamp: the instant as the service stamps it, to the minute (index.html)
            expect(f"{px}: `last confirmed` is the API's last_ok", f"last confirmed {a['last_ok'][:16].replace('T', ' ')}" in r["text"],
                   a["last_ok"])
        if a.get("last_target"):
            expect(f"{px}: the row names the last ping's target and outcome",
                   f"last ping {a['last_target']}: {a.get('last_outcome') or '—'}" in r["text"], None)
    expect(f"{px}: the page does not scroll sideways", w["scrollWidth"] <= w["innerWidth"], w)
    shot(page, "#cc-head", SHOTS / f"{'01' if px == 1280 else '03'}-{px}-cc-head.png")
    shot(page, "[data-cc-fleet]", SHOTS / f"{'02' if px == 1280 else '04'}-{px}-fleet-row.png")
    if px == 1280:
        shot(page, "[data-cc-fleet]", TMP / "control-1280-fleet-row-UNMASKED.png", masked=False)
        shot(page, "#cc-head", TMP / "control-1280-cc-head-UNMASKED.png", masked=False)


def main() -> None:
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        try:
            login(page)
            page.route("**/api/**", guard)
            who = page.evaluate("() => ({ user: data.whoami.user, cluster_admin: (data.whoami.visibility || {}).cluster_admin })")
            say("whoami", who)
            expect("developer holds the cluster-admin tier for the walk", who.get("cluster_admin") is True, who)
            got = page.evaluate("""async () => { const r = await fetch('/api/clusterconfigs?walk=epic-c-proofs', { credentials: 'same-origin' });
                return { http: r.status, body: r.ok ? await r.json() : await r.text() }; }""")
            expect("GET /api/clusterconfigs answers 200", got["http"] == 200, got["http"])
            fleet = got["body"].get("fleet") if got["http"] == 200 else {}
            write("api-clusterconfigs-fleet.json", {"read_at": utc(), "request": "GET /api/clusterconfigs",
                                                    "http": got["http"], "fleet": fleet})
            at_width(page, 1280, fleet or {})
            page.set_viewport_size({"width": 375, "height": 812})
            at_width(page, 375, fleet or {})
            expect("no uncaught page errors", not errors, errors)
            expect("no write was attempted", not blocked, blocked)
        except Exception as e:  # noqa: BLE001 — a walk defect is reported, then proof2.sh cleans up
            failures.append(f"exception: {type(e).__name__}")
            say("STOPPED on an exception", f"{type(e).__name__}: {e}")
        br.close()
    say("failures", failures)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
