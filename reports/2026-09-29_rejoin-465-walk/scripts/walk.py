#!/usr/bin/env python3
"""#465 on the deployed dashboard, as `developer` with the walk's temporary grant, at 1280 px: three Rejoins pressed
through the page's own Rejoin dialog on w465's card, after its Refresh answers auth_failed. Adapted from
reports/2026-09-28_rejoin-452-walk/scripts/walk.py.

    A  username developer, a random wrong password generated here (never printed; only its length is recorded)
    B  username developer, password `update` (one of Rejoin's own words)
    C  username developer, password `developer` (#447: inside the username)

Each press's HTTP status and JSON answer are read off the wire by Playwright's response listener (the request body,
which carries the password, is never read or written). A's answer is checked for the password, as typed and in its
Basic-header form, before it is written anywhere; after A and at the end the dashboard container's log since the walk
began is read into memory and searched the same way; only the counts are written.

The UI password comes from the environment only and is never printed: GSD_UI_PASSWORD (developer's, from `crc
console`). Subprocesses (oc) get an environment without it. GSD_WALK_T0 is the instant the walk began (run.sh).
The run exits non-zero on an uncaught page error, a visible "Dashboard API error", or a failed expectation."""
import base64, json, os, pathlib, re, secrets, string, subprocess, sys, time
from playwright.sync_api import sync_playwright

BASE = os.environ.get("GSD_BASE", "https://group-sync-dashboard.apps-crc.testing")
T0 = os.environ["GSD_WALK_T0"]
USER = "developer"
CID = "w465"
NS = "group-sync-dashboard"
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
SHOTS = ROOT / "screenshots"
ANSWERS = ROOT / "evidence" / "walk-rejoin-answers.json"
FLEET_NAME = "[data-cc-fleet] .v > .mono"          # masked in every screenshot, as the previous walks do
CLEAN_ENV = {k: v for k, v in os.environ.items() if k != "GSD_UI_PASSWORD"}
# A: 20 characters of letters and digits, drawn here; it lives only in this process's memory.
WRONG = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(20))
failures: list[str] = []
answers: list[dict] = []


class Stop(Exception):
    """A step answered differently from the brief: the walk stops here."""


def utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def say(tag: str, value) -> None:
    text = value if isinstance(value, str) else json.dumps(value)
    if WRONG in text:                                    # never print A's password, whatever answered it
        raise SystemExit("A's password reached the walk's output; stopped before printing it")
    print(f"{utc()} {tag:48s}: {re.sub(r'sha256~[A-Za-z0-9_-]+', 'sha256~<redacted>', text)}", flush=True)


def expect(what: str, ok: bool, detail) -> None:
    say(f"{'PASS' if ok else 'FAIL'} {what}", detail)
    if not ok:
        failures.append(what)
        raise Stop(what)


def forms(password: str) -> dict[str, str]:
    """The spellings searched for: the password as typed, and the RFC 7617 Basic value the login sends."""
    return {"as typed": password,
            "Basic value": base64.b64encode(f"{USER}:{password}".encode()).decode()}


def pod_log() -> str:
    """The dashboard container's log since the walk began, in memory only."""
    pod = subprocess.run(["oc", "get", "pods", "-n", NS, "-l", "app.kubernetes.io/name=group-sync-dashboard", "-o",
                          "jsonpath={.items[0].metadata.name}"], env=CLEAN_ENV, capture_output=True, text=True,
                         check=True).stdout.strip()
    return subprocess.run(["oc", "logs", "-n", NS, pod, "-c", "dashboard", "--timestamps", f"--since-time={T0}"],
                          env=CLEAN_ENV, capture_output=True, text=True, check=True, timeout=120).stdout


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


def row(page) -> dict:
    return page.evaluate("""async (cid) => { const r = await fetch('/api/clusterconfigs?walk=1', { credentials: 'same-origin' });
        if (!r.ok) return { http: r.status };
        const d = await r.json();
        const c = (d.clusters || []).find((x) => x.id === cid);
        return { http: r.status, row: c ? { id: c.id, api_url: c.api_url, credential: c.credential, status: c.status,
                                             rejoinable: c.rejoinable, retired: c.retired || false } : null }; }""", CID)


def card_facts(page) -> dict | None:
    return page.evaluate("""(cid) => { const c = document.getElementById('cc-cluster-' + cid);
        if (!c) return null;
        const t = (id) => { const e = document.getElementById(id); return e ? e.innerText.replace(/\\s+/g, ' ').trim() : null; };
        const rj = document.getElementById('cc-rejoin_' + cid);
        return { refresh: t('cc-refresh-result_' + cid), rejoin: t('cc-rejoin-result_' + cid),
                 rejoin_button: rj ? { text: rj.innerText.trim(), disabled: rj.disabled } : null }; }""", CID)


def dialog_facts(page) -> dict:
    """The dialog's state; the password field by its LENGTH only, never its value."""
    return page.evaluate("""() => { const d = document.getElementById('rejoin-dialog');
        return { open: d.open, cluster: d.dataset.cluster || null,
                 username_length: document.getElementById('rejoin-username').value.length,
                 password_length: document.getElementById('rejoin-password').value.length,
                 password_type: document.getElementById('rejoin-password').type,
                 message: document.getElementById('rejoin-msg').innerText.trim() }; }""")


def shot(page, selector: str, name: str) -> None:
    if selector == "#rejoin-dialog":
        assert dialog_facts(page)["password_length"] == 0, "the dialog is never captured with a typed password"
    el = page.locator(selector)
    el.scroll_into_view_if_needed(); page.wait_for_timeout(300)
    el.screenshot(path=str(SHOTS / name), mask=[page.locator(FLEET_NAME)])
    say("shot", name)


def open_clusters(page) -> None:
    page.goto(BASE + "/#page=clusters", wait_until="networkidle")
    page.wait_for_selector("#cc-head", timeout=30_000)
    page.wait_for_selector(f"#cc-cluster-{CID}", timeout=30_000)
    page.wait_for_timeout(1000)


def no_api_error(page, where: str) -> None:
    n = page.locator("text=Dashboard API error").count()
    expect(f"no 'Dashboard API error' ({where})", n == 0, n)


def press_refresh(page) -> dict:
    page.click(f"#cc-refresh_{CID}")
    page.wait_for_function("(cid) => { const r = document.getElementById('cc-refresh-result_' + cid);"
                           " return r && !/probing/.test(r.innerText); }", arg=CID, timeout=60_000)
    return card_facts(page)


def press_rejoin(page, case: str, password: str) -> dict:
    """Open the dialog on w465's card, type developer and the password, press Rejoin once; the wire's status and JSON
    answer, the card's and the dialog's text. The dialog is closed with Cancel afterwards (both fields emptied)."""
    page.click(f"#cc-rejoin_{CID}")
    page.wait_for_function("() => document.getElementById('rejoin-dialog').open", timeout=10_000)
    page.wait_for_timeout(300)
    d = dialog_facts(page)
    expect(f"{case}: the dialog opens for w465, both fields empty, the password field type=password",
           d["open"] and d["cluster"] == CID and d["username_length"] == 0 and d["password_length"] == 0
           and d["password_type"] == "password", d)
    page.fill("#rejoin-username", USER)
    page.fill("#rejoin-password", password)
    pressed = utc()
    with page.expect_response(lambda r: r.request.method == "POST"
                              and r.url.endswith(f"/api/clusterconfigs/{CID}/rejoin"), timeout=90_000) as info:
        page.click("#rejoin-go")
    response = info.value
    status, text = response.status, response.text()
    page.wait_for_function("(cid) => { const r = document.getElementById('cc-rejoin-result_' + cid);"
                           " return r && !/signing in once/.test(r.innerText); }", arg=CID, timeout=90_000)
    page.wait_for_timeout(800)
    if case == "A":
        hits = {k: text.count(v) for k, v in forms(password).items()}
        dom = page.evaluate("() => document.documentElement.outerHTML")
        dom_hits = {k: dom.count(v) for k, v in forms(password).items()}
        expect("A: the password occurs nowhere in the answer's bytes (as typed, as the Basic value)",
               not any(hits.values()), hits)
        expect("A: nor anywhere in the page's DOM once the answer is shown", not any(dom_hits.values()), dom_hits)
    card, dlg = card_facts(page), dialog_facts(page)
    record = {"case": case, "username": USER, "password": password if case in ("B", "C") else
              f"<{len(password)} random letters and digits, not recorded>", "pressed_at": pressed,
              "http_status": status, "answer": json.loads(text), "card_rejoin_line": card["rejoin"],
              "dialog_message": dlg["message"]}
    answers.append(record)
    ANSWERS.write_text(json.dumps(answers, indent=2) + "\n")
    say(f"{case}: pressed at", pressed)
    say(f"{case}: HTTP status", status)
    say(f"{case}: JSON answer", text)
    say(f"{case}: the card's Rejoin line", card["rejoin"])
    say(f"{case}: the dialog after the answer", dlg)
    return record


def close_dialog(page) -> None:
    page.click("#rejoin-cancel")
    page.wait_for_function("() => !document.getElementById('rejoin-dialog').open", timeout=10_000)
    page.wait_for_timeout(400)


def log_counts(tag: str, password: str) -> dict:
    log = pod_log()
    counts = {"lines": log.count("\n"), **{k: log.count(v) for k, v in forms(password).items()}}
    say(f"pod log since {T0}, A's password ({tag})", counts)
    return counts


def walk(page, errors: list) -> None:
    say("A's password", f"{len(WRONG)} characters, letters and digits, drawn by secrets.choice; never printed")
    who = whoami(page)
    say("whoami", who)
    expect("developer holds the cluster-admin tier for the walk", who["cluster_admin"] is True, who)
    open_clusters(page)
    no_api_error(page, "clusters tab")
    v = row(page)
    say("w465 before the Refresh", v)
    expect("w465 is served, polls auth_failed and is rejoinable",
           bool(v.get("row")) and v["row"]["status"] == "auth_failed" and v["row"]["rejoinable"] is True, v)
    f = press_refresh(page)
    say("Refresh answered", f)
    expect("Refresh answers auth_failed and the card offers Rejoin…",
           (f["refresh"] or "").startswith("Refresh: auth_failed") and "use Rejoin" in (f["refresh"] or "")
           and f["rejoin_button"] == {"text": "Rejoin…", "disabled": False}, f)
    shot(page, f"#cc-cluster-{CID}", "01-1280-card-offers-rejoin.png")

    # --- A: a wrong password, answered plainly ----------------------------------------------------------------
    a = press_rejoin(page, "A", WRONG)
    ans = a["answer"]
    expect("A: HTTP 200, outcome login-refused, the answer says w465 refused the password for developer",
           a["http_status"] == 200 and ans.get("outcome") == "login-refused"
           and ans.get("message", "").startswith(f"{CID} refused the password for {USER}"), [a["http_status"], ans])
    shot(page, "#rejoin-dialog", "02-1280-A-dialog-answer.png")
    close_dialog(page)
    shot(page, f"#cc-cluster-{CID}", "03-1280-A-card-answer.png")
    counts = log_counts("after A", WRONG)
    expect("A: the password occurs 0 times in the pod log since the walk began (as typed, as the Basic value)",
           counts["as typed"] == 0 and counts["Basic value"] == 0, counts)

    # --- B: a password that is one of Rejoin's own words ------------------------------------------------------
    b = press_rejoin(page, "B", "update")
    expect("B: not a 422 — sent, and CRC refuses it: HTTP 200 login-refused",
           b["http_status"] == 200 and b["answer"].get("outcome") == "login-refused", [b["http_status"], b["answer"]])
    close_dialog(page)
    shot(page, f"#cc-cluster-{CID}", "04-1280-B-card-answer.png")

    # --- C: #447, kept ----------------------------------------------------------------------------------------
    c = press_rejoin(page, "C", "developer")
    expect("C: HTTP 422 rejoin-password-within-username",
           c["http_status"] == 422 and str(c["answer"].get("detail", "")).startswith("rejoin-password-within-username:"),
           [c["http_status"], c["answer"]])
    shot(page, "#rejoin-dialog", "05-1280-C-dialog-answer.png")
    close_dialog(page)
    shot(page, f"#cc-cluster-{CID}", "06-1280-C-card-answer.png")

    counts = log_counts("at the end", WRONG)
    expect("A's password: 0 in the pod log at the end", counts["as typed"] == 0 and counts["Basic value"] == 0, counts)
    written = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file() and p.suffix in (".txt", ".json", ".md")
               and any(v in p.read_text(errors="replace") for v in forms(WRONG).values())]
    expect("A's password: 0 files under the walk's folder hold it", written == [], written)
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
            say("STOPPED on an exception", f"{type(e).__name__}: {str(e).replace(WRONG, '<A>')}")
        br.close()
    say("failures", failures)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
