#!/usr/bin/env python3
"""#316 Rejoin on the deployed dashboard, as `developer`: SPEC_D4 Appendix D steps 2-6 in one browser session.

    walk.py walk     step 2  the Add form writes `rejoin-walk` with a wrong token; the card polls auth_failed
                     step 3  Refresh answers auth_failed and offers Rejoin...; Rejoin as developer: rejoined;
                             Refresh then answers connected
                     step 4  the Secret, the pod log, the token counts (capture.sh); the cli login on the Logins tab
                     step 5  one wrong password, twice: login-refused, then login-refused "so it was not sent",
                             with the audit log counted after each press
                     step 6  once a fresh cluster-admin tier check is seen on the pod's /metrics, the binding is
                             removed and Rejoin pressed with the right password: not-cluster-admin
    walk.py after    a fresh login once the binding is gone: the tier the dashboard now answers

Secrets come from the environment only and are never printed: GSD_UI_PASSWORD (developer's, from `crc console`),
GSD_WRONG_PASSWORD (step 5's, random), GSD_WALK_TOKEN (the entry's wrong token, random). The dialog is
screenshotted only with its password field empty (asserted by its length, never read). Subprocesses (capture.sh,
oc) get an environment without those three. Every printed line is a measurement the README quotes; the run exits
non-zero on an uncaught page error, a visible "Dashboard API error", or a failed expectation, and stops at the
first failed step."""
import json, os, pathlib, re, subprocess, sys, time
from playwright.sync_api import sync_playwright

BASE = os.environ.get("GSD_BASE", "https://group-sync-dashboard.apps-crc.testing")
USER = "developer"
CID = os.environ.get("GSD_WALK_ENTRY", "rejoin-walk")      # run 1: rejoin-walk; run 2: rejoin-walk-2
RUN = os.environ.get("GSD_RUN", "")                        # run 2 prefixes its captures and screenshots with r2-
SERVER = "https://api.crc.testing:6443"
HOST = "dashboard"
RUN_LABEL = ("walk.gsd.lab/run", "rejoin-2026-09-27")
HERE = pathlib.Path(__file__).resolve().parent
SHOTS = HERE.parent / "screenshots"
EVIDENCE = HERE.parent / "evidence"
WIDTHS = [(1280, 900), (768, 1024), (375, 812)]
SECRET_ENV = ("GSD_UI_PASSWORD", "GSD_WRONG_PASSWORD", "GSD_WALK_TOKEN")
CLEAN_ENV = {k: v for k, v in os.environ.items() if k not in SECRET_ENV}
# say() also withholds the two RANDOM values by value. Not GSD_UI_PASSWORD: a lab password can equal an ordinary
# word (run 1's scrub-by-value withheld every "developer" it printed); it never reaches say() by construction.
SCRUB_ENV = ("GSD_WRONG_PASSWORD", "GSD_WALK_TOKEN")
failures: list[str] = []
shot_n = [0]


class Stop(Exception):
    """A step answered differently from the appendix: the walk stops here."""


def utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def say(tag: str, value) -> None:
    text = value if isinstance(value, str) else json.dumps(value)
    for k in SCRUB_ENV:                   # a belt to the braces: no secret is ever passed to say()
        if os.environ.get(k):
            text = text.replace(os.environ[k], "<withheld>")
    print(f"{utc()} {tag:40s}: {re.sub(r'sha256~[A-Za-z0-9_-]+', 'sha256~<redacted>', text)}", flush=True)


def expect(what: str, ok: bool, detail) -> None:
    say(f"{'PASS' if ok else 'FAIL'} {what}", detail)
    if not ok:
        failures.append(what)
        raise Stop(what)


def sh(*args: str) -> str:
    """A command with the secrets removed from its environment; its output, stripped."""
    r = subprocess.run(args, env=CLEAN_ENV, capture_output=True, text=True, timeout=180)
    return (r.stdout + r.stderr).strip()


def capture(kind: str, label: str, *extra: str) -> None:
    say("capture", sh(str(HERE / "capture.sh"), kind, RUN + label, *extra).splitlines()[-1])


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


def api_row(page) -> dict | None:
    # `?walk=1` marks the walk's own reads, so observation (b) can tell the page's poll from them
    return page.evaluate("""async (cid) => { const r = await fetch('/api/clusterconfigs?walk=1', { credentials: 'same-origin' });
        if (!r.ok) return { http: r.status };
        const c = ((await r.json()).clusters || []).find((x) => x.id === cid);
        return c ? { id: c.id, enabled: c.enabled, retired: c.retired, api_url: c.api_url, source: c.source,
                     credential: c.credential, status: c.status, rejoinable: c.rejoinable, error: c.error || null } : null; }""", CID)


def card_facts(page) -> dict | None:
    return page.evaluate("""(cid) => { const c = document.getElementById('cc-cluster-' + cid);
        if (!c) return null;
        const t = (id) => { const e = document.getElementById(id); return e ? e.innerText.replace(/\\s+/g, ' ').trim() : null; };
        const rj = document.getElementById('cc-rejoin-' + cid);
        return { refresh: t('cc-refresh-result-' + cid), rejoin: t('cc-rejoin-result-' + cid),
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
    """One capture per width, all on this page: the view state (the Refresh and Rejoin answers) survives a resize."""
    for width, height in WIDTHS:
        page.set_viewport_size({"width": width, "height": height})
        page.wait_for_timeout(400)
        if selector == "#rejoin-dialog":
            assert dialog_facts(page)["password_length"] == 0, "the dialog is never captured with a typed password"
        el = page.locator(selector)
        el.scroll_into_view_if_needed(); page.wait_for_timeout(200)
        shot_n[0] += 1
        fname = f"{RUN}{shot_n[0]:02d}-{width}-{name}.png"
        el.screenshot(path=str(SHOTS / fname))
        say("shot", fname)
    page.set_viewport_size({"width": 1280, "height": 900})
    page.wait_for_timeout(300)


def open_clusters(page) -> None:
    page.goto(BASE + "/#page=clusters", wait_until="networkidle")
    page.wait_for_selector("#cc-head", timeout=30_000)
    page.wait_for_selector("[data-cc-cluster]", timeout=30_000)
    page.wait_for_timeout(1000)


def to_clusters_in_page(page) -> None:
    """Back to the tab by hash, without a reload: `view` (the answers on the card) is kept."""
    page.evaluate("() => { location.hash = '#page=clusters'; }")
    page.wait_for_selector(f"#cc-cluster-{CID}", timeout=30_000)
    page.wait_for_timeout(800)


def no_api_error(page, where: str) -> None:
    n = page.locator("text=Dashboard API error").count()
    expect(f"no 'Dashboard API error' ({where})", n == 0, n)


def press_refresh(page) -> dict:
    page.click(f"#cc-refresh-{CID}")
    page.wait_for_function("(cid) => { const r = document.getElementById('cc-refresh-result-' + cid);"
                           " return r && !/probing/.test(r.innerText); }", arg=CID, timeout=60_000)
    return card_facts(page)


def press_rejoin(page, password_env: str) -> tuple[dict, dict]:
    """Type developer and the password named by `password_env` into the open dialog, press once, wait for the answer."""
    page.fill("#rejoin-username", USER)
    page.fill("#rejoin-password", os.environ[password_env])
    t = utc()
    page.click("#rejoin-go")
    page.wait_for_function("(cid) => { const r = document.getElementById('cc-rejoin-result-' + cid);"
                           " return r && !/signing in once/.test(r.innerText); }", arg=CID, timeout=90_000)
    page.wait_for_timeout(500)
    card, dlg = card_facts(page), dialog_facts(page)
    say("rejoin pressed at", t)
    say("rejoin answer on the card", card["rejoin"])
    say("dialog after the answer", dlg)
    return card, dlg


def open_dialog(page) -> None:
    page.click(f"#cc-rejoin-{CID}")
    page.wait_for_function("() => document.getElementById('rejoin-dialog').open", timeout=10_000)
    page.wait_for_timeout(300)


def close_dialog(page) -> None:
    """Cancel: the card behind the modal is captured only once the dialog is closed (Cancel clears both fields)."""
    page.click("#rejoin-cancel")
    page.wait_for_function("() => !document.getElementById('rejoin-dialog').open", timeout=10_000)
    page.wait_for_timeout(300)


def logins_shot(page, at: str) -> None:
    """The Logins tab: the attempts table's header, then the walker's cli row at `at` (the table shows fmtTime's local)."""
    page.wait_for_selector("table tbody tr", timeout=30_000); page.wait_for_timeout(1000)
    local = page.evaluate("(iso) => fmtTime(iso)", at)
    row = page.locator("table tbody tr", has_text="cli allow via openshift-challenging-client") \
        .filter(has_text=USER).filter(has_text=local).first
    say("Logins row, as the table shows it", row.inner_text().replace("\n", " ").replace("\t", " "))
    for name, el in (("logins-header", row.locator("xpath=ancestor::table[1]/thead")), ("logins-cli-row", row)):
        el.scroll_into_view_if_needed(); page.wait_for_timeout(300)
        shot_n[0] += 1
        fname = f"{RUN}{shot_n[0]:02d}-1280-step4-{name}.png"
        el.screenshot(path=str(SHOTS / fname))
        say("shot", fname)


def dialog_reach(page) -> dict:
    """Where the dialog's two buttons are, and whether a tap at each one's centre lands on it."""
    return page.evaluate("""() => { const d = document.getElementById('rejoin-dialog'), cs = getComputedStyle(d);
        const at = (id) => { const b = document.getElementById(id), r = b.getBoundingClientRect();
          const x = r.left + r.width / 2, y = r.top + r.height / 2;
          const inView = r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth;
          const hit = inView ? document.elementFromPoint(x, y) : null;
          return { top: Math.round(r.top), bottom: Math.round(r.bottom), in_viewport: inView, tap_lands: !!hit && (hit === b || b.contains(hit)) }; };
        const r = d.getBoundingClientRect();
        return { viewport: [innerWidth, innerHeight], dialog_top: Math.round(r.top), dialog_bottom: Math.round(r.bottom),
                 overflow_y: cs.overflowY, max_height: cs.maxHeight, scroll_height: d.scrollHeight, client_height: d.clientHeight,
                 scroll_top: Math.round(d.scrollTop), page_scroll_y: Math.round(scrollY),
                 cancel: at('rejoin-cancel'), rejoin: at('rejoin-go') }; }""")


def observe_dialog_reach(page) -> None:
    """Observation (a): at 375 px, can a person reach Cancel and Rejoin? A wheel scroll over the open dialog, as a
    finger would, then a hit test at each button's centre. The dialog is empty throughout (asserted)."""
    for width, height in ((375, 812), (375, 667)):
        page.set_viewport_size({"width": width, "height": height}); page.wait_for_timeout(500)
        assert dialog_facts(page)["password_length"] == 0
        before = dialog_reach(page)
        say(f"obs (a) {width}x{height} before scrolling", before)
        shot_n[0] += 1; name = f"{RUN}{shot_n[0]:02d}-{width}x{height}-obs-a-dialog-before-scroll.png"
        page.screenshot(path=str(SHOTS / name)); say("shot", name)
        page.mouse.move(width / 2, height / 2)
        page.mouse.wheel(0, 3000); page.wait_for_timeout(800)
        after = dialog_reach(page)
        say(f"obs (a) {width}x{height} after a wheel scroll", after)
        shot_n[0] += 1; name = f"{RUN}{shot_n[0]:02d}-{width}x{height}-obs-a-dialog-after-scroll.png"
        page.screenshot(path=str(SHOTS / name)); say("shot", name)
        reach = after["cancel"]["tap_lands"] and after["rejoin"]["tap_lands"]
        say(f"obs (a) {width}x{height}: Cancel and Rejoin reachable", reach)
        page.evaluate("() => { document.getElementById('rejoin-dialog').scrollTop = 0; }")
    page.set_viewport_size({"width": 1280, "height": 900}); page.wait_for_timeout(400)


def connection_text(page) -> str | None:
    return page.evaluate("""(cid) => { const c = document.getElementById('cc-cluster-' + cid); if (!c) return null;
        const kv = [...c.querySelectorAll('.cc-kv')].find((k) => k.querySelector('.k').textContent.trim() === 'connection');
        if (!kv) return null;
        const t = kv.querySelector('.v').innerText.replace(/\\s+/g, ' ').trim();
        return t.split(' Refresh:')[0]; }""", CID)


def observe_connection_redraw(page, answered: float) -> None:
    """Observation (b): after `rejoined`, does the card's CONNECTION row leave `auth_failed` on the page's next poll?
    Watched without any reload for two POLL_INTERVAL_MS (60 s) plus 15 s from the answer; the page's own GET
    /api/clusterconfigs are told from the walk's (`?walk=1`) and listed with their instants."""
    polls: list[str] = []
    def on_response(r):
        u = r.url
        if r.request.method == "GET" and "/api/clusterconfigs" in u and "walk=1" not in u and "/api/clusterconfigs/" not in u:
            polls.append(utc())
    page.on("response", on_response)
    deadline = answered + 135
    seen = connection_text(page)
    say("obs (b) CONNECTION row now", seen)
    while time.time() < deadline and "auth_failed" in (seen or ""):
        page.wait_for_timeout(5_000)
        seen = connection_text(page)
    page.remove_listener("response", on_response)
    say("obs (b) the page's own GET /api/clusterconfigs since watching", polls)
    say("obs (b) CONNECTION row at the end", [utc(), round(time.time() - answered, 1), seen])
    say("obs (b) redrawn from auth_failed within two poll intervals", "auth_failed" not in (seen or ""))
    shot(page, f"#cc-cluster-{CID}", "obs-b-connection-after-poll")


def tier_allowed() -> int:
    out = sh("oc", "exec", "-n", "group-sync-dashboard", "deploy/group-sync-dashboard", "-c", "dashboard", "--",
             "python3.14", "-c", "import urllib.request; print(urllib.request.urlopen("
             "'http://127.0.0.1:8080/metrics').read().decode())")
    m = re.search(r'gsd_visibility_tier_checks_total\{outcome="allowed",threshold="cluster_admin"\} (\d+)', out)
    return int(m.group(1)) if m else -1


def add_entry(page) -> None:
    """Step 2: the Add form writes the entry — the server, the random wrong token, the trusted bundle, the label."""
    expect(f"no {CID} entry before the walk", api_row(page) is None, api_row(page))
    page.fill("#cc-name", CID)
    page.fill("#cc-server", SERVER)
    page.fill("#cc-token", os.environ["GSD_WALK_TOKEN"])
    page.check("#cc-ca-trustedBundle"); page.wait_for_timeout(500)
    page.fill("#cc-label-key", RUN_LABEL[0]); page.fill("#cc-label-val", RUN_LABEL[1])
    page.click("#cc-label-add"); page.wait_for_timeout(500)
    say("the form's YAML twin", page.locator("#cc-yaml").inner_text())
    form = page.locator("#cc-add")
    form.scroll_into_view_if_needed(); shot_n[0] += 1
    form.screenshot(path=str(SHOTS / f"{RUN}{shot_n[0]:02d}-1280-step2-add-form.png"))
    say("shot", f"{RUN}{shot_n[0]:02d}-1280-step2-add-form.png")
    page.click("#cc-create")
    page.wait_for_function("() => !/Creating/.test(document.getElementById('cc-form-msg').innerText)"
                           " && document.getElementById('cc-form-msg').innerText.trim() !== ''", timeout=30_000)
    msg = page.locator("#cc-form-msg").inner_text().strip()
    say("Create Secret answered", msg)
    expect(f"the Add form created gsd-cluster-{CID}", msg.startswith(f"Secret gsd-cluster-{CID} created"), msg)
    capture("secret", "step2")


def walk(page, errors: list) -> None:
    walk_start = utc()
    who = whoami(page)
    say("whoami", who)
    expect("developer holds the cluster-admin tier for the walk", who["cluster_admin"] is True, who)

    # --- step 2: the throwaway entry, through the Add form -------------------------------------------------
    open_clusters(page)
    if os.environ.get("GSD_STEP2_DONE") == "1":
        # A previous invocation's Add form already wrote the entry (its output and step-2 capture record it):
        # this one resumes at the poll, and a re-run's shot numbers continue after that invocation's.
        shot_n[0] = int(os.environ.get("GSD_SHOT_FROM", "0"))
        say("step 2 done by the previous invocation; the row now", api_row(page))
    else:
        add_entry(page)
    deadline, row = time.time() + 420, None
    while time.time() < deadline:
        row = api_row(page)
        if row and row.get("status") not in (None, "", "never", "pending"):
            break
        page.wait_for_timeout(10_000)
    say("rejoin-walk row once polled", row)
    expect("the card polls auth_failed", bool(row) and row["status"] == "auth_failed", row)
    expect("the row is rejoinable", row["rejoinable"] is True, row)

    # --- step 3: Refresh, then Rejoin ----------------------------------------------------------------------
    open_clusters(page)
    f = press_refresh(page)
    say("Refresh answered", f)
    expect("Refresh answers auth_failed and the card offers Rejoin…",
           (f["refresh"] or "").startswith("Refresh: auth_failed") and "use Rejoin" in (f["refresh"] or "")
           and f["rejoin_button"] == {"text": "Rejoin…", "disabled": False}, f)
    shot(page, f"#cc-cluster-{CID}", "step3-card-offers-rejoin")
    open_dialog(page)
    d = dialog_facts(page)
    say("dialog opened", d)
    expect("the dialog opens for rejoin-walk, both fields empty, the password field type=password",
           d["open"] and d["cluster"] == CID and d["username_length"] == 0 and d["password_length"] == 0
           and d["password_type"] == "password", d)
    shot(page, "#rejoin-dialog", "step3-dialog-empty")
    observe_dialog_reach(page)
    card, dlg = press_rejoin(page, "GSD_UI_PASSWORD")
    answered = time.time()
    expect("Rejoin answers rejoined and the dialog closes",
           (card["rejoin"] or "").startswith("Rejoin: rejoined") and not dlg["open"]
           and dlg["password_length"] == 0 and dlg["username_length"] == 0, [card["rejoin"], dlg])
    shot(page, f"#cc-cluster-{CID}", "step3-rejoined")
    deadline = time.time() + 180
    while time.time() < deadline:
        row = api_row(page)
        if row and row["status"] == "ok":
            break
        page.wait_for_timeout(5_000)
    say("rejoin-walk row after the Rejoin", row)
    expect("the poller reads rejoin-walk again: status ok", bool(row) and row["status"] == "ok", row)
    f = press_refresh(page)
    say("Refresh after the Rejoin", f)
    expect("Refresh answers connected, the Rejoin answer still shown",
           bool(re.match(r"^Refresh: connected · \d{4}-\d{2}-\d{2}T", f["refresh"] or ""))
           and (f["rejoin"] or "").startswith("Rejoin: rejoined"), f)
    shot(page, f"#cc-cluster-{CID}", "step3-refresh-connected")
    observe_connection_redraw(page, answered)

    # --- step 4: the evidence --------------------------------------------------------------------------------
    for kind in ("secret", "tokens"):
        capture(kind, "step4")
    capture("podlog", "step4", walk_start)
    rejoin_at = walk_start
    deadline, rows = time.time() + 420, []
    while time.time() < deadline:
        got = page.evaluate("""async ([host, since, cid]) => { const out = {};
            for (const id of [host, cid]) {
              const r = await fetch('/api/clusters/' + id + '/logins', { credentials: 'same-origin' });
              if (!r.ok) { out[id] = { http: r.status }; continue; }
              const d = await r.json();
              out[id] = { http: r.status, rows: (d.attempts || []).filter((x) => x.user_name === 'developer'
                && x.at >= since && /cli allow via openshift-challenging-client/.test(x.detail || ''))
                .map((x) => ({ at: x.at, outcome: x.outcome, provider: x.provider, detail: x.detail })) }; }
            return out; }""", [HOST, rejoin_at, CID])
        rows = (got.get(HOST) or {}).get("rows") or []
        if rows:
            break
        page.wait_for_timeout(15_000)
    say("Logins API: developer cli allows since the walk began", got)
    expect("the walker's cli login is a Logins row", bool(rows), rows)
    page.evaluate("() => { location.hash = '#page=logins'; }")
    logins_shot(page, rows[0]["at"])
    to_clusters_in_page(page)

    # --- step 5: one wrong password, twice, on one pod --------------------------------------------------------
    t5 = utc()
    capture("audit", "step5-before", t5)
    open_dialog(page)
    card, dlg = press_rejoin(page, "GSD_WRONG_PASSWORD")
    expect("the first wrong password: login-refused, sent (the remote refused it), dialog open, field empty",
           (card["rejoin"] or "").startswith("Rejoin: login-refused") and "refused the password for developer"
           in card["rejoin"] and dlg["open"] and dlg["password_length"] == 0, [card["rejoin"], dlg])
    shot(page, "#rejoin-dialog", "step5-first-refused-dialog")
    close_dialog(page)
    shot(page, f"#cc-cluster-{CID}", "step5-first-refused-card")
    page.wait_for_timeout(8_000)
    capture("audit", "step5-after-first", t5)
    open_dialog(page)
    card, dlg = press_rejoin(page, "GSD_WRONG_PASSWORD")
    expect("the same wrong password again: login-refused, 'so it was not sent'",
           (card["rejoin"] or "").startswith("Rejoin: login-refused") and "so it was not sent" in card["rejoin"]
           and dlg["open"] and dlg["password_length"] == 0, [card["rejoin"], dlg])
    shot(page, "#rejoin-dialog", "step5-second-not-sent-dialog")
    close_dialog(page)
    shot(page, f"#cc-cluster-{CID}", "step5-second-not-sent-card")
    page.wait_for_timeout(8_000)
    capture("audit", "step5-after-second", t5)
    capture("tokens", "step5")

    # --- step 6: the remote's no -------------------------------------------------------------------------------
    capture("secret", "step6-before"); capture("tokens", "step6-before")
    fresh_at = None
    for _ in range(20):
        t0 = time.time()                  # before the read: the fresh check can be no earlier than this
        before = tier_allowed()
        page.evaluate("async () => (await fetch('/api/whoami', { credentials: 'same-origin' })).status")
        after = tier_allowed()
        say("cluster_admin allowed checks around a /api/whoami", [before, after])
        if after > before >= 0:
            fresh_at = t0
            break
        page.wait_for_timeout(5_000)
    expect("a fresh cluster-admin tier check seen (the 60 s cache starts now)", fresh_at is not None, fresh_at)
    say("fresh tier check at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(fresh_at)))
    out = sh("oc", "delete", "clusterrolebindings.rbac.authorization.k8s.io", "-l", "=".join(RUN_LABEL))
    (EVIDENCE / f"{RUN}step6-grant-delete.txt").write_text(f"# oc delete clusterrolebindings.rbac.authorization.k8s.io -l "
                                                     f"{'='.join(RUN_LABEL)}\n# at {utc()}\n{out}\n")
    say("binding removed", out)
    for _ in range(10):
        cani = sh("oc", "auth", "can-i", "update", "clusterrolebindings.rbac.authorization.k8s.io", "--as=developer")
        if "no" in [line.strip() for line in cani.splitlines()]:   # stdout's answer; stderr's warning follows it
            break
        time.sleep(1)
    say("can-i update clusterrolebindings --as=developer", [line for line in cani.splitlines() if line.strip()])
    elapsed = time.time() - fresh_at
    expect("still inside the host's cached tier (under 40 s since the fresh check)", elapsed < 40, round(elapsed, 1))
    open_dialog(page)
    card, dlg = press_rejoin(page, "GSD_UI_PASSWORD")
    say("seconds since the fresh tier check at the answer", round(time.time() - fresh_at, 1))
    expect("the right password without the binding: not-cluster-admin",
           (card["rejoin"] or "").startswith("Rejoin: not-cluster-admin") and dlg["password_length"] == 0,
           [card["rejoin"], dlg])
    shot(page, "#rejoin-dialog", "step6-not-cluster-admin-dialog")
    close_dialog(page)
    shot(page, f"#cc-cluster-{CID}", "step6-not-cluster-admin-card")
    capture("secret", "step6-after"); capture("tokens", "step6-after"); capture("tiers", "step6-after")
    capture("podlog", "step6", walk_start)
    expect("no uncaught page errors", not errors, errors)


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "walk"
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        login(page)
        if mode == "logins":                   # step 4's Logins capture on its own: walk.py logins <the row's at>
            shot_n[0] = int(os.environ.get("GSD_SHOT_FROM", "0"))
            page.goto(BASE + "/#page=logins", wait_until="networkidle")
            try:
                logins_shot(page, sys.argv[2])
            except Exception as e:  # noqa: BLE001
                failures.append(f"exception: {type(e).__name__}")
                say("STOPPED on an exception", f"{type(e).__name__}: {str(e).splitlines()[0]}")
        elif mode == "after":
            who = whoami(page)
            status = page.evaluate("async () => (await fetch('/api/clusterconfigs', { credentials: 'same-origin' })).status")
            tabs = page.evaluate("() => [...document.querySelectorAll('button.tab')].map(b => b.textContent.trim())")
            say("whoami", who); say("/api/clusterconfigs", status)
            try:
                expect("after the binding's removal: no cluster-admin tier, no tab, /api/clusterconfigs 403",
                       who["cluster_admin"] is False and status == 403
                       and not any("Cluster Configurations" in t for t in tabs), [who, status])
            except Stop:
                pass
        else:
            try:
                walk(page, errors)
            except Stop as e:
                say("STOPPED at", str(e))
            except Exception as e:  # noqa: BLE001 — a walk defect is reported, then the shell cleans up
                failures.append(f"exception: {type(e).__name__}")
                say("STOPPED on an exception", f"{type(e).__name__}: {e}")
        br.close()
    say("failures", failures)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
