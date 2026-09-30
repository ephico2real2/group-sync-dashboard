#!/usr/bin/env python3
"""#244 (CA visibility) on the deployed dashboard, as `developer` with the walk's temporary grant, at 1280 px.
Adapted from reports/2026-09-29_rejoin-465-walk/scripts/walk.py.

    A  mock-privateca (caData): the card's tls row and the entry's `trust` object
    B  mock-trusted (the trusted bundle), mock-selfsigned (insecure), shared-rnd: tls rows, trust objects, warnings
    C  w244-fail (a caData that did not sign the server): the raw error, the fix and the store on the card and in the
       API; the log's action and store extracted from the pod log for the byte-for-byte comparison run.sh makes
    D  w244-exp (a 10-day CA): the `ca-expiring` warning in the API and the banner
    E  the Add-cluster form's Test connection, pressed twice: the wrong CA of C pasted as PEM, then `not a
       certificate`; each POST /api/clusterconfigs/test's status and JSON read off the wire

The page is DRIVEN for the tab, the cards, the banner and the form (E). The API entries are read with the page's own
`fetch('/api/clusterconfigs')` on the logged-in session. The UI password comes from the environment only
(GSD_UI_PASSWORD) and is never printed; subprocesses (oc) get an environment without it. E's bearer token is random,
never printed, and appended to $GSD_WALK_TMP/tokens so the pod log can be searched for it. Everything written passes
`clean()`: `sha256~` values and the fleet account's name are replaced. The run exits non-zero on an uncaught page
error, a visible "Dashboard API error", or a failed expectation."""
import base64, json, os, pathlib, re, secrets, subprocess, sys, time
from playwright.sync_api import sync_playwright

BASE = os.environ.get("GSD_BASE", "https://group-sync-dashboard.apps-crc.testing")
T0 = os.environ["GSD_WALK_T0"]
TMP = pathlib.Path(os.environ["GSD_WALK_TMP"])
USER = "developer"
NS = "group-sync-dashboard"
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
SHOTS = ROOT / "screenshots"
EV = ROOT / "evidence"
FLEET_NAME = "[data-cc-fleet] .v > .mono"          # masked in every screenshot, as the previous walks do
CLEAN_ENV = {k: v for k, v in os.environ.items() if k != "GSD_UI_PASSWORD"}
TEST_TOKEN = "sha256~" + secrets.token_hex(22)     # E's bearer token: bogus, never printed
failures: list[str] = []


class Stop(Exception):
    """A step answered differently from the brief: the walk stops here."""


def oc(*args: str) -> str:
    return subprocess.run(["oc", *args], env=CLEAN_ENV, capture_output=True, text=True, check=True,
                          timeout=120).stdout


FLEET = json.loads(oc("get", "leases.coordination.k8s.io", "-n", NS, "-l",
                      "groupsync-dashboard.io/lease-type=fleet-account", "-o", "json"))["items"][0][
    "metadata"]["annotations"]["groupsync-dashboard.io/account"]


# C, D and E use mock-privateca's own server URL, read from its Secret.
SERVER = base64.b64decode(json.loads(oc("get", "secrets", "-n", NS, "gsd-cluster-mock-privateca", "-o", "json"))[
    "data"]["server"]).decode()


def clean(text: str) -> str:
    if TEST_TOKEN in text:
        raise SystemExit("E's bearer token reached the walk's output; stopped before writing it")
    text = re.sub(r"sha256~[A-Za-z0-9_-]+", "sha256~<redacted>", text)
    return re.sub(re.escape(FLEET), "<fleet account>", text, flags=re.I)


def utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def say(tag: str, value) -> None:
    text = value if isinstance(value, str) else json.dumps(value)
    print(clean(f"{utc()} {tag:58s}: {text}"), flush=True)


def write(name: str, value, raw: bool = False) -> None:
    """evidence/<name>: JSON (indented) or, with raw=True, the string's exact bytes (no newline added)."""
    text = value if raw else json.dumps(value, indent=2) + "\n"
    (EV / name).write_text(clean(text))
    say("wrote", f"evidence/{name}")


def expect(what: str, ok: bool, detail) -> None:
    say(f"{'PASS' if ok else 'FAIL'} {what}", detail)
    if not ok:
        failures.append(what)
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


def api(page) -> dict:
    """GET /api/clusterconfigs with the page's own fetch on the logged-in session."""
    return page.evaluate("""async () => { const r = await fetch('/api/clusterconfigs?walk=244', { credentials: 'same-origin' });
        return { http: r.status, body: r.ok ? await r.json() : await r.text() }; }""")


def entry(body: dict, cid: str) -> dict | None:
    """The fields #244 touches on one row; the credential's kind only (the API never serves its value)."""
    for c in body.get("clusters", []):
        if c["id"] == cid:
            return {k: c.get(k) for k in ("id", "source", "api_url", "credential", "tls", "status", "last_poll",
                                          "error", "trust", "action", "store") if k in c}
    return None


def card(page, cid: str) -> dict | None:
    return page.evaluate("""(cid) => { const c = document.getElementById('cc-cluster-' + cid);
        if (!c) return null;
        const t = (e) => e ? e.innerText.replace(/\\s+/g, ' ').trim() : null;
        // textContent, not innerText: `.cc-kv .k` is `text-transform: uppercase` (app.css), so innerText reads "TLS"
        const row = (k) => { const r = [...c.querySelectorAll('.cc-kv')].find((x) => ((x.querySelector('.k') || {}).textContent || '').trim() === k);
                             return r ? r.querySelector('.v') : null; };
        const tls = row('tls'), conn = row('connection');
        return { tls_row: t(tls),
                 trust_store: t(tls && tls.querySelector('.cc-trust-store')),
                 certificates: [...(tls ? tls.querySelectorAll('.cc-ca-cert') : [])].map((e) => ({ text: t(e), data_cc_ca: e.dataset.ccCa })),
                 badges: [...(tls ? tls.querySelectorAll('.badge, [class*="badge"]') : [])].map(t),
                 connection_error: t(conn && conn.querySelector('.err')),
                 action: (conn && conn.querySelector('[data-cc-tls-action]')) ? conn.querySelector('[data-cc-tls-action]').innerText : null,
                 store: t(conn && conn.querySelector('[data-cc-tls-store]')),
                 connection_row: t(conn) }; }""", cid)


def banner(page) -> list[dict]:
    return page.evaluate("""() => [...document.querySelectorAll('[data-cc-warning]')].map((e) => ({
        code: e.dataset.ccWarning, title: (e.querySelector('strong') || {}).innerText || null,
        text: e.innerText.replace(/\\s+/g, ' ').trim() }))""")


def shot(page, selector: str, name: str) -> None:
    el = page.locator(selector).first
    el.scroll_into_view_if_needed(); page.wait_for_timeout(300)
    el.screenshot(path=str(SHOTS / name), mask=[page.locator(FLEET_NAME), page.locator("#cc-token")])
    say("shot", name)


def open_clusters(page, need: list[str]) -> None:
    page.goto(BASE + "/#page=clusters", wait_until="networkidle")
    page.wait_for_selector("#cc-head", timeout=30_000)
    for cid in need:
        page.wait_for_selector(f"#cc-cluster-{cid}", timeout=30_000)
    page.wait_for_timeout(1000)


def no_api_error(page, where: str) -> None:
    n = page.locator("text=Dashboard API error").count()
    expect(f"no 'Dashboard API error' ({where})", n == 0, n)


def pod_log() -> str:
    pod = oc("get", "pods", "-n", NS, "-l", "app.kubernetes.io/name=group-sync-dashboard", "-o",
             "jsonpath={.items[0].metadata.name}").strip()
    return oc("logs", "-n", NS, pod, "-c", "dashboard", "--timestamps", f"--since-time={T0}")


def log_field(line: str, key: str) -> str | None:
    """One key's value from an events.py line: `key="…"` when quoted (a quote inside is written as '), else `key=…`."""
    m = re.search(rf' {key}=(?:"([^"]*)"|(\S+))', line)
    return None if m is None else (m.group(1) if m.group(1) is not None else m.group(2))


def cluster_secret_names() -> list[str]:
    return sorted(oc("get", "secrets", "-n", NS, "-l", "groupsync-dashboard.io/secret-type=cluster",
                     "-o", "jsonpath={range .items[*]}{.metadata.name}{'\\n'}{end}").split())


def press_test(page, case: str, pem: str) -> dict:
    """Fill the Add-cluster form (caData mode, the PEM given) and press Test connection once; the wire's status and
    JSON answer, and what the form shows afterwards. Create is never pressed."""
    page.click("#cc-ca-caData"); page.wait_for_timeout(300)
    page.fill("#cc-name", "w244-test")
    page.fill("#cc-server", SERVER)
    page.fill("#cc-token", TEST_TOKEN)
    page.fill("#cc-ca-pem", pem)
    pressed = utc()
    with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith("/api/clusterconfigs/test"),
                              timeout=90_000) as info:
        page.click("#cc-test")
    response = info.value
    status, text = response.status, response.text()
    page.wait_for_function("() => !document.getElementById('cc-test-result') || !/Testing/.test(document.getElementById('cc-test-result').innerText)",
                           timeout=90_000)
    page.wait_for_timeout(800)
    shown = page.evaluate("""() => { const t = (e) => e ? e.innerText.replace(/\\s+/g, ' ').trim() : null;
        const r = document.getElementById('cc-test-result');
        return { test_result: t(r), certificates: [...(r ? r.querySelectorAll('.cc-ca-cert') : [])].map(t),
                 form_message: t(document.getElementById('cc-form-msg')) }; }""")
    record = {"case": case, "pressed_at": pressed, "request": {"name": "w244-test", "server": SERVER,
              "credential": "bearerToken (random, not recorded)", "tls.mode": "caData",
              "tls.caData": "base64 of the PEM field (the page's ccBody)",
              "pem_field": pem if case == "E2" else "the wrong CA of step C (evidence/generated-cas.txt)"},
              "http_status": status, "answer": json.loads(text), "page_shows": shown}
    say(f"{case}: HTTP status", status)
    say(f"{case}: JSON answer", text)
    say(f"{case}: the page shows", shown)
    return record


def walk(page, errors: list) -> None:
    who = page.evaluate("() => ({ user: data.whoami.user, tier: data.whoami.tier,"
                        " cluster_admin: (data.whoami.visibility || {}).cluster_admin })")
    say("whoami", who)
    expect("developer holds the cluster-admin tier for the walk", who["cluster_admin"] is True, who)
    open_clusters(page, ["mock-privateca", "mock-trusted", "mock-selfsigned", "shared-rnd", "w244-fail", "w244-exp"])
    no_api_error(page, "clusters tab")
    got = api(page)
    expect("GET /api/clusterconfigs answers 200", got["http"] == 200, got["http"])
    body = got["body"]
    write("walk-clusterconfigs-entries.json", {"read_at": utc(), "http": got["http"],
                                                "clusters": [entry(body, c["id"]) for c in body["clusters"]],
                                                "warnings": body.get("warnings")})

    # --- A: mock-privateca --------------------------------------------------------------------------------------
    a, ac = entry(body, "mock-privateca"), card(page, "mock-privateca")
    write("A-mock-privateca-trust.json", a["trust"])
    write("A-mock-privateca-card.json", ac)
    certs = a["trust"]["certificates"]
    expect("A: trust is caData from the Secret, one certificate listed with subject, issuer, dates, sha256, validity",
           a["tls"]["ca"] == "caData" and a["trust"]["sourceKind"] == "secret" and len(certs) >= 1
           and all(k in certs[0] for k in ("subject", "issuer", "notBefore", "notAfter", "sha256", "validity")),
           a["trust"])
    expect("A: the card's tls row names the store and count and lists each certificate's subject, issuer and notAfter",
           ac["trust_store"] == f"store {a['trust']['store']} · {a['trust']['count']} certificate"
           + ("" if a["trust"]["count"] == 1 else "s")
           and len(ac["certificates"]) == len(certs)
           and all(c["subject"] in s["text"] and c["issuer"] in s["text"] and c["notAfter"] in s["text"]
                   for c, s in zip(certs, ac["certificates"])), ac)
    shot(page, "#cc-cluster-mock-privateca", "01-1280-A-mock-privateca-card.png")

    # --- B: the other modes, as they are -----------------------------------------------------------------------
    b = {cid: {"entry": entry(body, cid), "card": card(page, cid)} for cid in ("mock-trusted", "mock-selfsigned", "shared-rnd")}
    b["warning_codes"] = sorted({w["code"] for w in body.get("warnings", [])})
    write("B-other-modes.json", b)
    expect("B: no ca-not-enterprise warning while the pin is empty",
           "ca-not-enterprise" not in b["warning_codes"], b["warning_codes"])
    shot(page, "#cc-cluster-mock-trusted", "02-1280-B-mock-trusted-card.png")

    # --- C: a verify failure shows the fix ---------------------------------------------------------------------
    c, cc = entry(body, "w244-fail"), card(page, "w244-fail")
    write("C-w244-fail-entry.json", c)
    write("C-w244-fail-card.json", cc)
    expect("C: the entry keeps the raw CERTIFICATE_VERIFY_FAILED error and carries action and store",
           "CERTIFICATE_VERIFY_FAILED" in (c.get("error") or "") and bool(c.get("action")) and bool(c.get("store")), c)
    expect("C: the card shows the raw error, the action and the store under it",
           "CERTIFICATE_VERIFY_FAILED" in (cc["connection_error"] or "") and cc["action"] == c["action"]
           and cc["store"] == f"store {c['store']}", cc)
    write("C-action-api.txt", c["action"], raw=True)
    write("C-store-api.txt", c["store"], raw=True)
    log = pod_log()
    lines = [ln for ln in log.splitlines() if " cluster=w244-fail " in ln and "outcome=cert-verify-failed" in ln]
    expect("C: the pod log holds a cert-verify-failed line for w244-fail", bool(lines), len(lines))
    write("C-log-line.txt", lines[0] + "\n", raw=True)
    write("C-action-log.txt", log_field(lines[0], "action"), raw=True)
    write("C-store-log.txt", log_field(lines[0], "store"), raw=True)
    shot(page, "#cc-cluster-w244-fail", "03-1280-C-w244-fail-card.png")

    # --- D: the expiry warning ---------------------------------------------------------------------------------
    d, dc = entry(body, "w244-exp"), card(page, "w244-exp")
    warns = [w for w in body.get("warnings", []) if w["code"] == "ca-expiring"]
    shown = banner(page)
    write("D-w244-exp.json", {"entry": d, "card": dc, "api_ca_expiring": warns, "banner": shown})
    expect("D: the API carries a ca-expiring warning for w244-exp",
           any(w["clusters"] == ["w244-exp"] for w in warns), warns)
    expect("D: the banner shows it under its own title",
           any(s["code"] == "ca-expiring" and s["title"] == "CA expiring." for s in shown), shown)
    expd = [ln for ln in log.splitlines() if " ca-expiring " in ln and "clusters=w244-exp" in ln]
    write("D-log-announcement.txt", "\n".join(expd) + "\n", raw=True)
    shot(page, "#cc-head", "04-1280-D-warnings-banner.png")
    shot(page, "#cc-cluster-w244-exp", "05-1280-D-w244-exp-card.png")

    # --- E: the Test response carries the summary ---------------------------------------------------------------
    before = cluster_secret_names()
    with TMP.joinpath("tokens").open("a") as fh:
        fh.write(TEST_TOKEN + "\n")
    wrong = (TMP / "wrong-ca.pem").read_text()
    page.locator("#cc-add").scroll_into_view_if_needed()
    e1 = press_test(page, "E1", wrong)
    expect("E1: HTTP 200, reachable false, the verify error, and certificates with subject, issuer, notAfter",
           e1["http_status"] == 200 and e1["answer"].get("reachable") is False
           and "CERTIFICATE_VERIFY_FAILED" in (e1["answer"].get("error") or "")
           and any(x.get("subject") == "CN=walk-244 wrong CA" and x.get("issuer") and x.get("notAfter")
                   for x in e1["answer"].get("certificates", [])), e1["answer"])
    shot(page, "#cc-test-result", "06-1280-E1-test-result.png")
    e2 = press_test(page, "E2", "not a certificate")
    expect("E2: HTTP 422, the ca-data-invalid refusal", e2["http_status"] == 422
           and str(e2["answer"].get("detail", "")).startswith("ca-data-invalid"), e2["answer"])
    shot(page, "#cc-form-msg", "07-1280-E2-refusal.png")
    after = cluster_secret_names()
    write("E-test-answers.json", {"E1": e1, "E2": e2, "cluster_secrets_before_E": before,
                                  "cluster_secrets_after_E": after})
    expect("E: Test saved nothing — the cluster Secrets are the same before and after, no gsd-cluster-w244-test",
           before == after and "gsd-cluster-w244-test" not in after, {"before": before, "after": after})

    no_api_error(page, "the end")
    expect("no uncaught page errors", not errors, errors)


def main() -> None:
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        login(page)
        try:
            walk(page, errors)
        except Stop as e:
            say("STOPPED at", str(e))
        except Exception as e:  # noqa: BLE001 — a walk defect is reported, then run.sh cleans up
            failures.append(f"exception: {type(e).__name__}")
            say("STOPPED on an exception", f"{type(e).__name__}: {e}")
        br.close()
    say("failures", failures)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
