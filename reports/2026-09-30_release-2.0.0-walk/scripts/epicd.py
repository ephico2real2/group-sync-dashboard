#!/usr/bin/env python3
"""Epic D's surfaces on the deployed Cluster Configurations tab, as `developer` (after
reports/2026-09-30_chip-492-walk/scripts/walk.py and reports/2026-09-28_batch-1110-walk/scripts/walk.py). One mode per
run, named by argv[1]:

    precheck  before the grant: developer's tier, the tabs offered, what GET /api/clusterconfigs answers, and what the
              Reports tab paints (the catalogue or a refusal) — so the README can say why the grant was taken
    live      with the grant, at 1280 px then 375 px:
                every live card's TLS row (chip, store, certificates, expiry) and connection row; the API entries;
                the shared-API-URL banner (`[data-cc-warning]`) against the API's `warnings`;
                Refresh pressed ONCE on mock-privateca at 1280 px, its answer line read, and every cluster Secret's
                resourceVersion read with oc just before the press and just after the answer

A route guard lets every GET to /api/clusterconfigs through and exactly one write, POST
/api/clusterconfigs/mock-privateca/refresh; any other request to that API is aborted and fails the walk, so Rejoin,
Rotate, Delete and Create cannot be pressed by accident. shared-qa's card is read and photographed, never clicked.

The UI password comes from the environment only (GSD_UI_PASSWORD) and is never printed; oc runs without it. Every
screenshot masks the fleet row and any element naming the fleet account (evidence/mask-log.jsonl has the counts);
everything written passes clean(). Exits non-zero on an uncaught page error, a visible "Dashboard API error", a blocked
write, or a failed expectation; a failed expectation is recorded and the walk goes on."""
import json, os, pathlib, re, subprocess, sys, time
from playwright.sync_api import sync_playwright

BASE = os.environ.get("GSD_BASE", "https://group-sync-dashboard.apps-crc.testing")
USER = "developer"
NS = "group-sync-dashboard"
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
SHOTS = ROOT / "screenshots"
EV = ROOT / "evidence"
MASK_LOG = EV / "mask-log.jsonl"
FLEET_ROW = "[data-cc-fleet] .v > .mono"
REFRESHED = "mock-privateca"
NEVER = {"shared-qa"}                     # the operator's rule: its card is never clicked
CLEAN_ENV = {k: v for k, v in os.environ.items() if k != "GSD_UI_PASSWORD"}
failures: list[str] = []
blocked: list[str] = []
refresh_posts: list[str] = []


class Stop(Exception):
    """A precondition failed: the walk cannot go on."""


def oc(*args: str) -> str:
    return subprocess.run(["oc", *args], env=CLEAN_ENV, capture_output=True, text=True, check=True,
                          timeout=120).stdout


FLEET = json.loads(oc("get", "leases.coordination.k8s.io", "-n", NS, "-l",
                      "groupsync-dashboard.io/lease-type=fleet-account", "-o", "json"))["items"][0][
    "metadata"]["annotations"]["groupsync-dashboard.io/account"]
FLEET_RE = re.compile(re.escape(FLEET), re.I)


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


def need(what: str, ok: bool, detail) -> None:
    expect(what, ok, detail)
    if not ok:
        raise Stop(what)


def guard(route) -> None:
    """GETs pass; one POST …/mock-privateca/refresh passes; anything else is aborted and recorded."""
    req = route.request
    path = req.url.split("?")[0]
    if req.method == "GET":
        route.continue_()
    elif req.method == "POST" and path.endswith(f"/api/clusterconfigs/{REFRESHED}/refresh") and not refresh_posts:
        refresh_posts.append(f"{utc()} {req.method} {path}")
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
    return page.evaluate("() => ({ user: data.whoami.user, cluster_admin: (data.whoami.visibility || {}).cluster_admin,"
                         " host_scope: (data.whoami.visibility || {}).scope })")


def tabs(page) -> list[str]:
    return page.evaluate("() => [...document.querySelectorAll('nav.tabs .tab')].map((e) => e.innerText.trim())")


def api(page) -> dict:
    """GET /api/clusterconfigs with the page's own fetch on the logged-in session."""
    return page.evaluate("""async () => { const r = await fetch('/api/clusterconfigs?walk=200', { credentials: 'same-origin' });
        return { http: r.status, body: r.ok ? await r.json() : await r.text() }; }""")


FIELDS = ("id", "source", "retired", "enabled", "api_url", "credential", "tls", "status", "last_poll", "error",
          "action", "store", "trust")


def entry(body: dict, cid: str) -> dict | None:
    """The fields Epic D reads on one row; the credential's kind only (the API never serves its value)."""
    for c in body.get("clusters", []):
        if c["id"] == cid:
            return {k: c.get(k) for k in FIELDS if k in c}
    return None


def card(page, cid: str) -> dict | None:
    return page.evaluate("""(cid) => { const c = document.getElementById('cc-cluster-' + cid);
        if (!c) return null;
        const t = (e) => e ? e.innerText.replace(/\\s+/g, ' ').trim() : null;
        // textContent, not innerText: `.cc-kv .k` is `text-transform: uppercase` (app.css)
        const row = (k) => { const r = [...c.querySelectorAll('.cc-kv')].find((x) => ((x.querySelector('.k') || {}).textContent || '').trim() === k);
                             return r ? r.querySelector('.v') : null; };
        const tls = row('tls'), conn = row('connection'), h2 = c.querySelector('h2');
        const chips = tls ? [...tls.querySelectorAll('.badge')] : [];
        return { heading: t(h2), shared_api_chip: !!h2 && /shared API URL/.test(h2.innerText),
                 shared_api_hint: t(c.querySelector('.cc-shared-api-hint')),
                 tls_row: t(tls), badges: chips.map((e) => ({ text: t(e), class: e.className })),
                 connection_row: t(conn),
                 refresh_button: !!document.getElementById('cc-refresh_' + cid),
                 rejoin_button: !!document.getElementById('cc-rejoin_' + cid),
                 refresh_line: t(document.getElementById('cc-refresh-result_' + cid)) }; }""", cid)


def banners(page) -> list[str]:
    return page.evaluate("() => [...document.querySelectorAll('[data-cc-warning]')].map((e) => e.innerText.replace(/\\s+/g, ' ').trim())")


def page_width(page) -> dict:
    return page.evaluate("() => ({ innerWidth: window.innerWidth, scrollWidth: document.documentElement.scrollWidth })")


def secret_rvs() -> dict:
    items = json.loads(oc("get", "secrets", "-n", NS, "-l", "groupsync-dashboard.io/secret-type=cluster", "-o",
                          "json"))["items"]
    return {"read_at": utc(), "resourceVersions": {i["metadata"]["name"]: i["metadata"]["resourceVersion"] for i in items}}


def shot(page, selector: str, name: str) -> None:
    el = page.locator(selector).first
    el.scroll_into_view_if_needed(); page.wait_for_timeout(300)
    row, named = page.locator(FLEET_ROW), page.get_by_text(FLEET_RE)
    with MASK_LOG.open("a") as f:
        f.write(json.dumps({"shot": f"screenshots/{name}", "fleet_row_elements": row.count(),
                            "elements_naming_the_account": named.count(),
                            "page_text_named_the_account": bool(FLEET_RE.search(page.locator("body").inner_text()))}) + "\n")
    el.screenshot(path=str(SHOTS / name), mask=[row, named])
    say("shot", f"screenshots/{name}")


def open_clusters(page, need_ids: list[str]) -> None:
    page.goto(BASE + "/#page=clusters", wait_until="networkidle")
    page.wait_for_selector("#cc-head", timeout=30_000)
    for cid in need_ids:
        page.wait_for_selector(f"#cc-cluster-{cid}", timeout=30_000)
    page.wait_for_function("() => !document.getElementById('main').classList.contains('stale')", timeout=30_000)
    page.wait_for_timeout(800)


def no_api_error(page, where: str) -> None:
    n = page.locator("text=Dashboard API error").count()
    expect(f"no 'Dashboard API error' ({where})", n == 0, n)


def texts(c: dict) -> list[str]:
    return [b["text"] for b in c["badges"]]


def precheck(page) -> None:
    who = whoami(page)
    offered = tabs(page)
    got = api(page)
    page.click('button.tab:text-is("Reports")')
    page.wait_for_selector("#report-picker, .scope-refusal", timeout=30_000)
    page.wait_for_timeout(600)
    picker = page.locator("#report-picker").count() > 0
    refusal = page.locator(".scope-refusal").first.inner_text() if not picker else None
    write("P-precheck.json", {"read_at": utc(), "whoami": who, "tabs": offered,
                              "cluster_configurations_tab_offered": "Cluster Configurations" in offered,
                              "kpis_tab_offered": "KPIs" in offered,
                              "api_clusterconfigs": {"http": got["http"],
                                                     "body": got["body"] if got["http"] != 200 else "(200: not kept)"},
                              "reports_tab": {"catalogue_offered": picker,
                                              "refusal": " ".join(refusal.split()) if refusal else None}})
    shot(page, "#main", "00-1280-precheck-reports-without-grant.png")


def live_1280(page) -> None:
    who = whoami(page)
    say("whoami", who)
    need("developer holds the cluster-admin tier for the walk", who["cluster_admin"] is True, who)
    say("tabs offered", tabs(page))
    ids = ["mock-privateca", "mock-selfsigned", "mock-trusted", "shared-rnd", "shared-qa"]
    open_clusters(page, ids)
    no_api_error(page, "clusters tab, 1280")
    got = api(page)
    need("GET /api/clusterconfigs answers 200", got["http"] == 200, got["http"])
    body = got["body"]
    live_ids = [c["id"] for c in body["clusters"] if not c.get("retired")]
    retired_ids = [c["id"] for c in body["clusters"] if c.get("retired")]
    write("clusterconfigs-1280.json", {"read_at": utc(), "http": got["http"], "warnings": body.get("warnings"),
                                       "live": live_ids, "retired": retired_ids,
                                       "clusters": [entry(body, cid) for cid in live_ids]})

    # --- the shared-API-URL banner, against the API's own warnings ---------------------------------------------
    shown = banners(page)
    say("API warnings (all kinds)", body.get("warnings"))
    say("API shared-api-url warnings", [w for w in (body.get("warnings") or []) if w.get("code") == "shared-api-url"])
    say("banners painted", shown)
    expect("one banner per API warning (the banner is painted from the API's warnings)",
           len(shown) == len(body.get("warnings") or []), {"warnings": len(body.get("warnings") or []), "banners": len(shown)})
    shot(page, "#cc-head", "01-1280-head-and-banner.png")

    # --- every live card's TLS row ------------------------------------------------------------------------------
    cards = {cid: card(page, cid) for cid in live_ids if cid != "dashboard"}
    cards["dashboard"] = card(page, "dashboard")
    write("cards-1280.json", {"read_at": utc(), "cards": cards, "page": page_width(page)})
    pc, pe = cards["mock-privateca"], entry(body, "mock-privateca")
    na = [c.get("notAfter") for c in ((pe.get("trust") or {}).get("certificates") or [])]
    expect("mock-privateca: the TLS chip is the green `verified`, `ca: caData`, a store and a certificate line",
           pc["badges"][:1] == [{"text": "verified", "class": "badge ok"}] and "ca: caData" in (pc["tls_row"] or "")
           and "store" in (pc["tls_row"] or "") and "certificate" in (pc["tls_row"] or ""), pc["tls_row"])
    expect("mock-privateca: the card names the certificate's expiry (the API's notAfter)",
           bool(na) and all(str(x)[:10] in (pc["tls_row"] or "") for x in na), {"notAfter": na})
    expect("mock-selfsigned: the TLS chips are exactly `insecure`", texts(cards["mock-selfsigned"]) == ["insecure"],
           cards["mock-selfsigned"]["badges"])
    for cid in ("mock-trusted", "shared-rnd", "shared-qa"):
        say(f"recorded: {cid} chips / tls row", [texts(cards[cid]), cards[cid]["tls_row"]])
    for i, cid in enumerate(("mock-privateca", "mock-selfsigned", "mock-trusted", "shared-rnd", "shared-qa"), 2):
        shot(page, f"#cc-cluster-{cid}", f"{i:02d}-1280-{cid}-card.png")

    # --- Refresh, pressed once on mock-privateca ------------------------------------------------------------------
    before = secret_rvs()
    say("before the press: cluster Secret resourceVersions", before)
    page.click(f"#cc-refresh_{REFRESHED}")
    page.wait_for_function("(cid) => { const r = document.getElementById('cc-refresh-result_' + cid);"
                           " return r && !/probing/.test(r.innerText); }", arg=REFRESHED, timeout=60_000)
    after_card = card(page, REFRESHED)
    after = secret_rvs()
    say("after the answer: cluster Secret resourceVersions", after)
    say("refresh answer line", after_card["refresh_line"])
    write("refresh-mock-privateca.json", {"pressed": refresh_posts, "answer_line": after_card["refresh_line"],
                                          "card_after": after_card, "secrets_before": before, "secrets_after": after})
    expect("Refresh was sent exactly once", len(refresh_posts) == 1, refresh_posts)
    expect("Refresh answered on mock-privateca's own card (`Refresh: connected · …`)",
           bool(re.match(r"^Refresh: connected · ", after_card["refresh_line"] or "")), after_card["refresh_line"])
    expect("no cluster Secret changed across the press (every resourceVersion equal)",
           before["resourceVersions"] == after["resourceVersions"], None)
    shot(page, f"#cc-cluster-{REFRESHED}", "07-1280-mock-privateca-after-refresh.png")


def live_375(page) -> None:
    open_clusters(page, ["mock-privateca", "mock-selfsigned"])
    no_api_error(page, "clusters tab, 375")
    width = page_width(page)
    got = {cid: card(page, cid) for cid in ("mock-privateca", "mock-selfsigned")}
    write("cards-375.json", {"read_at": utc(), "cards": got, "banners": banners(page), "page": width})
    expect("375: mock-privateca `verified`, mock-selfsigned `insecure`",
           texts(got["mock-privateca"])[:1] == ["verified"] and texts(got["mock-selfsigned"]) == ["insecure"],
           {k: texts(v) for k, v in got.items()})
    expect("375: the page does not scroll sideways (scrollWidth <= innerWidth)",
           width["scrollWidth"] <= width["innerWidth"], width)
    shot(page, "#cc-head", "08-375-head-and-banner.png")
    shot(page, "#cc-cluster-mock-privateca", "09-375-mock-privateca-card.png")
    shot(page, "#cc-cluster-mock-selfsigned", "10-375-mock-selfsigned-card.png")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in ("precheck", "live"):
        raise SystemExit("usage: epicd.py precheck|live")
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        page.route("**/api/clusterconfigs**", guard)
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        try:
            login(page)
            if mode == "precheck":
                precheck(page)
            else:
                live_1280(page)
                page.set_viewport_size({"width": 375, "height": 812})
                live_375(page)
            no_api_error(page, "the end")
            expect("no uncaught page errors", not errors, errors)
            expect("no write other than the one Refresh was attempted", not blocked, blocked)
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
