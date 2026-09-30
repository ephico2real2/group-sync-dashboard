#!/usr/bin/env python3
"""#492 (the `verify failed` chip) on the deployed dashboard, as `developer`, at 1280 px and 375 px.
Cut down from reports/2026-09-29_ca-244-walk/scripts/walk.py. One mode per run, named by argv[1]:

    precheck  before the grant: developer's tier, whether the Cluster Configurations tab is offered, what
              GET /api/clusterconfigs answers and what /#page=clusters paints — so the README can say why the grant
              was taken
    live      with the grant, after w492-fail's first poll:
                A  w492-fail (a caData that did not sign the server): `verify failed` (warning) on the tls row, no
                   `.badge.ok` there, `ca: caData` kept; the connection row keeps CERTIFICATE_VERIFY_FAILED and the
                   fix sentence; the API entry carries `action` — at 1280 px and at 375 px (scrollWidth recorded)
                B  mock-privateca: green `verified`, `ca: caData`, no `action` in its entry
                C  mock-selfsigned: `insecure`, no `verified`, no `verify failed`
                D  mock-trusted and shared-rnd: their chips, recorded only
    retired   with the grant, after discovery removed w492-fail: its retired entry and card (E), and the #244
              walk's retired rows as they are on this version, recorded only

The page is DRIVEN for the tab and the cards; the API entries are read with the page's own
`fetch('/api/clusterconfigs')` on the logged-in session. The UI password comes from the environment only
(GSD_UI_PASSWORD) and is never printed; subprocesses (oc) get an environment without it. Everything written passes
`clean()`: `sha256~` values and the fleet account's name are replaced. The run exits non-zero on an uncaught page
error, a visible "Dashboard API error", or a failed expectation; a failed expectation is recorded and the walk goes
on, so one miss does not hide the rest."""
import json, os, pathlib, re, subprocess, sys, time
from playwright.sync_api import sync_playwright

BASE = os.environ.get("GSD_BASE", "https://group-sync-dashboard.apps-crc.testing")
TMP = pathlib.Path(os.environ["GSD_WALK_TMP"])
USER = "developer"
NS = "group-sync-dashboard"
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
SHOTS = ROOT / "screenshots"
EV = ROOT / "evidence"
FLEET_NAME = "[data-cc-fleet] .v > .mono"          # masked in every screenshot, as the previous walks do
CLEAN_ENV = {k: v for k, v in os.environ.items() if k != "GSD_UI_PASSWORD"}
TOKENS = [t for t in (TMP / "tokens").read_text().split() if t] if (TMP / "tokens").exists() else []
failures: list[str] = []


class Stop(Exception):
    """A precondition failed: the walk cannot go on."""


def oc(*args: str) -> str:
    return subprocess.run(["oc", *args], env=CLEAN_ENV, capture_output=True, text=True, check=True,
                          timeout=120).stdout


FLEET = json.loads(oc("get", "leases.coordination.k8s.io", "-n", NS, "-l",
                      "groupsync-dashboard.io/lease-type=fleet-account", "-o", "json"))["items"][0][
    "metadata"]["annotations"]["groupsync-dashboard.io/account"]


def clean(text: str) -> str:
    if any(t in text for t in TOKENS):
        raise SystemExit("the walk's bearer token reached the walk's output; stopped before writing it")
    text = re.sub(r"sha256~[A-Za-z0-9_-]+", "sha256~<redacted>", text)
    return re.sub(re.escape(FLEET), "<fleet account>", text, flags=re.I)


def utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def say(tag: str, value) -> None:
    text = value if isinstance(value, str) else json.dumps(value)
    print(clean(f"{utc()} {tag:58s}: {text}"), flush=True)


def write(name: str, value) -> None:
    (EV / name).write_text(clean(json.dumps(value, indent=2) + "\n"))
    say("wrote", f"evidence/{name}")


def expect(what: str, ok: bool, detail) -> None:
    say(f"{'PASS' if ok else 'FAIL'} {what}", detail)
    if not ok:
        failures.append(what)


def need(what: str, ok: bool, detail) -> None:
    expect(what, ok, detail)
    if not ok:
        raise Stop(what)


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


def api(page) -> dict:
    """GET /api/clusterconfigs with the page's own fetch on the logged-in session."""
    return page.evaluate("""async () => { const r = await fetch('/api/clusterconfigs?walk=492', { credentials: 'same-origin' });
        return { http: r.status, body: r.ok ? await r.json() : await r.text() }; }""")


def entry(body: dict, cid: str) -> dict | None:
    """The fields #492 reads on one row; the credential's kind only (the API never serves its value)."""
    for c in body.get("clusters", []):
        if c["id"] == cid:
            return {k: c.get(k) for k in ("id", "source", "retired", "enabled", "api_url", "credential", "tls",
                                          "status", "last_poll", "error", "action", "store") if k in c}
    return None


def card(page, cid: str) -> dict | None:
    return page.evaluate("""(cid) => { const c = document.getElementById('cc-cluster-' + cid);
        if (!c) return null;
        const t = (e) => e ? e.innerText.replace(/\\s+/g, ' ').trim() : null;
        // textContent, not innerText: `.cc-kv .k` is `text-transform: uppercase` (app.css), so innerText reads "TLS"
        const row = (k) => { const r = [...c.querySelectorAll('.cc-kv')].find((x) => ((x.querySelector('.k') || {}).textContent || '').trim() === k);
                             return r ? r.querySelector('.v') : null; };
        const tls = row('tls'), conn = row('connection');
        const box = (e) => { if (!e) return null; const r = e.getBoundingClientRect();
                             return { left: Math.round(r.left), right: Math.round(r.right), top: Math.round(r.top), bottom: Math.round(r.bottom) }; };
        const chips = tls ? [...tls.querySelectorAll('.badge')] : [];
        return { tls_row: t(tls),
                 badges: chips.map((e) => ({ text: t(e), class: e.className })),
                 ok_badges_in_tls_row: tls ? tls.querySelectorAll('.badge.ok').length : null,
                 connection_error: t(conn && conn.querySelector('.err')),
                 action: (conn && conn.querySelector('[data-cc-tls-action]')) ? conn.querySelector('[data-cc-tls-action]').innerText : null,
                 store: t(conn && conn.querySelector('[data-cc-tls-store]')),
                 connection_row: t(conn),
                 geometry: { card: box(c), card_scrollWidth: c.scrollWidth, card_clientWidth: c.clientWidth,
                             tls_value: box(tls), chips: chips.map(box) } }; }""", cid)


def page_width(page) -> dict:
    return page.evaluate("() => ({ innerWidth: window.innerWidth, scrollWidth: document.documentElement.scrollWidth })")


def shot(page, selector: str, name: str) -> None:
    el = page.locator(selector).first
    el.scroll_into_view_if_needed(); page.wait_for_timeout(300)
    el.screenshot(path=str(SHOTS / name), mask=[page.locator(FLEET_NAME), page.locator("#cc-token")])
    say("shot", name)


def open_clusters(page, need_ids: list[str]) -> None:
    page.goto(BASE + "/#page=clusters", wait_until="networkidle")
    page.wait_for_selector("#cc-head", timeout=30_000)
    for cid in need_ids:
        page.wait_for_selector(f"#cc-cluster-{cid}", timeout=30_000)
    page.wait_for_timeout(1000)


def no_api_error(page, where: str) -> None:
    n = page.locator("text=Dashboard API error").count()
    expect(f"no 'Dashboard API error' ({where})", n == 0, n)


def texts(c: dict) -> list[str]:
    return [b["text"] for b in c["badges"]]


def precheck(page) -> None:
    who = whoami(page)
    tabs = page.evaluate("() => [...document.querySelectorAll('nav.tabs .tab')].map((e) => e.innerText.trim())")
    got = api(page)
    page.goto(BASE + "/#page=clusters", wait_until="networkidle")
    page.wait_for_timeout(2000)
    painted = page.evaluate("() => { const m = document.querySelector('main') || document.body;"
                            " return { cc_head: !!document.getElementById('cc-head'),"
                            " cards: document.querySelectorAll('.cc-cluster').length,"
                            " text: m.innerText.replace(/\\s+/g, ' ').trim().slice(0, 600) }; }")
    write("P-precheck.json", {"read_at": utc(), "whoami": who, "tabs": tabs,
                              "cluster_configurations_tab_offered": "Cluster Configurations" in tabs,
                              "api_clusterconfigs": {"http": got["http"],
                                                     "body": got["body"] if got["http"] != 200 else "(200: not kept)"},
                              "page_clusters": painted})
    shot(page, "main", "00-1280-precheck-clusters-without-grant.png")


def live_1280(page) -> None:
    who = whoami(page)
    say("whoami", who)
    need("developer holds the cluster-admin tier for the walk", who["cluster_admin"] is True, who)
    ids = ["w492-fail", "mock-privateca", "mock-selfsigned", "mock-trusted", "shared-rnd"]
    open_clusters(page, ids)
    no_api_error(page, "clusters tab, 1280")
    got = api(page)
    need("GET /api/clusterconfigs answers 200", got["http"] == 200, got["http"])
    body = got["body"]
    write("live-clusterconfigs-entries.json", {"read_at": utc(), "http": got["http"],
                                               "clusters": [entry(body, c["id"]) for c in body["clusters"]]})

    # --- A: w492-fail -----------------------------------------------------------------------------------------
    a, ac = entry(body, "w492-fail"), card(page, "w492-fail")
    write("A-w492-fail-1280.json", {"entry": a, "card": ac, "page": page_width(page)})
    expect("A: the entry keeps CERTIFICATE_VERIFY_FAILED and carries action, tls caData not insecure",
           "CERTIFICATE_VERIFY_FAILED" in (a.get("error") or "") and bool(a.get("action"))
           and a["tls"] == {"insecure": False, "ca": "caData"}, a)
    expect("A: the tls row's one chip is `verify failed`, class `badge warning`",
           ac["badges"] == [{"text": "verify failed", "class": "badge warning"}], ac["badges"])
    expect("A: no .badge.ok in the tls row", ac["ok_badges_in_tls_row"] == 0, ac["ok_badges_in_tls_row"])
    expect("A: `ca: caData` beside the chip", "ca: caData" in (ac["tls_row"] or ""), ac["tls_row"])
    expect("A: the connection row keeps CERTIFICATE_VERIFY_FAILED and the fix sentence (= the API's action)",
           "CERTIFICATE_VERIFY_FAILED" in (ac["connection_error"] or "") and ac["action"] == a["action"], ac)
    shot(page, "#cc-cluster-w492-fail", "01-1280-A-w492-fail-card.png")

    # --- B: mock-privateca ------------------------------------------------------------------------------------
    b, bc = entry(body, "mock-privateca"), card(page, "mock-privateca")
    write("B-mock-privateca-1280.json", {"entry": b, "card": bc})
    expect("B: the entry has no action; tls caData not insecure", "action" not in b
           and b["tls"] == {"insecure": False, "ca": "caData"}, b)
    expect("B: the tls row's chips: `verified`, class `badge ok`; no `verify failed`",
           bc["badges"][:1] == [{"text": "verified", "class": "badge ok"}] and "verify failed" not in texts(bc),
           bc["badges"])
    expect("B: `ca: caData` beside the chip", "ca: caData" in (bc["tls_row"] or ""), bc["tls_row"])
    shot(page, "#cc-cluster-mock-privateca", "02-1280-B-mock-privateca-card.png")

    # --- C: mock-selfsigned -----------------------------------------------------------------------------------
    c, cc = entry(body, "mock-selfsigned"), card(page, "mock-selfsigned")
    write("C-mock-selfsigned-1280.json", {"entry": c, "card": cc})
    expect("C: the tls row's chips are exactly `insecure`; no `verified`, no `verify failed`",
           texts(cc) == ["insecure"], cc["badges"])
    shot(page, "#cc-cluster-mock-selfsigned", "03-1280-C-mock-selfsigned-card.png")

    # --- D: the trusted bundle, recorded only -----------------------------------------------------------------
    d = {cid: {"entry": entry(body, cid), "card": card(page, cid)} for cid in ("mock-trusted", "shared-rnd")}
    write("D-trusted-bundle-1280.json", d)
    for cid, v in d.items():
        say(f"D (recorded): {cid} chips / status / action", [texts(v["card"]), v["entry"].get("status"),
                                                              v["entry"].get("action")])


def live_375(page) -> None:
    open_clusters(page, ["w492-fail", "mock-privateca", "mock-selfsigned"])
    no_api_error(page, "clusters tab, 375")
    got = api(page)
    need("GET /api/clusterconfigs answers 200 (375)", got["http"] == 200, got["http"])
    a, ac = entry(got["body"], "w492-fail"), card(page, "w492-fail")
    width = page_width(page)
    write("A-w492-fail-375.json", {"read_at": utc(), "entry": a, "card": ac, "page": width,
                                   "mock-privateca": card(page, "mock-privateca"),
                                   "mock-selfsigned": card(page, "mock-selfsigned")})
    expect("A 375: the tls row's one chip is `verify failed`, class `badge warning`; no .badge.ok",
           ac["badges"] == [{"text": "verify failed", "class": "badge warning"}] and ac["ok_badges_in_tls_row"] == 0,
           ac["badges"])
    expect("A 375: the page does not scroll sideways (scrollWidth <= innerWidth)",
           width["scrollWidth"] <= width["innerWidth"], width)
    g = ac["geometry"]
    expect("A 375: the chip sits inside the card (chip.left >= card.left, chip.right <= card.right)",
           all(ch["left"] >= g["card"]["left"] and ch["right"] <= g["card"]["right"] for ch in g["chips"]), g)
    shot(page, "#cc-cluster-w492-fail", "04-375-A-w492-fail-card.png")
    shot(page, "#cc-cluster-mock-privateca", "05-375-B-mock-privateca-card.png")
    shot(page, "#cc-cluster-mock-selfsigned", "06-375-C-mock-selfsigned-card.png")


def retired(page) -> None:
    who = whoami(page)
    need("developer holds the cluster-admin tier for the retired pass", who["cluster_admin"] is True, who)
    open_clusters(page, ["w492-fail"])
    no_api_error(page, "clusters tab, retired pass")
    got = api(page)
    need("GET /api/clusterconfigs answers 200 (retired pass)", got["http"] == 200, got["http"])
    body = got["body"]
    e, ec = entry(body, "w492-fail"), card(page, "w492-fail")
    history = {cid: {"entry": entry(body, cid), "card": card(page, cid)} for cid in ("w244-fail", "w244-exp")}
    write("E-w492-fail-retired.json", {"read_at": utc(), "entry": e, "card": ec, "w244_rows_recorded_only": history})
    expect("E: the entry is retired, with tls null and no action", e.get("retired") is True and e.get("tls") is None
           and not e.get("action"), e)
    expect("E: the retired card's tls row paints no chip", ec["badges"] == [], ec)
    shot(page, "#cc-cluster-w492-fail", "07-1280-E-w492-fail-retired-card.png")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in ("precheck", "live", "retired"):
        raise SystemExit("usage: walk.py precheck|live|retired")
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        try:
            login(page)
            if mode == "precheck":
                precheck(page)
            elif mode == "live":
                live_1280(page)
                page.set_viewport_size({"width": 375, "height": 812})
                live_375(page)
            else:
                retired(page)
            no_api_error(page, "the end")
            expect("no uncaught page errors", not errors, errors)
        except Stop as e:
            say("STOPPED at", str(e))
        except Exception as e:  # noqa: BLE001 — a walk defect is reported, then run.sh cleans up
            failures.append(f"exception: {type(e).__name__}")
            say("STOPPED on an exception", f"{type(e).__name__}: {e}")
        br.close()
    say(f"{mode} failures", failures)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
