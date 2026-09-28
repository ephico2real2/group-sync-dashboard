#!/usr/bin/env python3
"""#473, #467, #462 and #459 on the deployed Cluster Configurations tab (application 1.16.0), as `developer`.

    walk.py walk <discovery evidence>
        at 1280, 768 and 375 px, then 320 px for #473 alone:
        #459  the `constructor` card, idle: no `Refresh:` line, no `Rejoin:` line, no Rejoin button; after its
              Refresh answers auth_failed, Rejoin is offered like on any other card;
        #473  the Findings card's `gsd-cluster-mock-refusal` detail, read line by line from the text's Range client
              rects (as the PR's test does): below 520 px every line ends between words and the label sits above the
              value; at 768 and 1280 the row keeps two columns;
        #467  the discovery line `N served from Secrets · M labelled Secret(s) refused (see Findings)`: N against the
              clusters the page serves from a Secret and against discovery's last `accepted=`, M against the Findings
              card and discovery's last `refused=` (read from <discovery evidence>, a `capture.sh discovery` file);
        #462  a page-wide id check (no duplicate; every per-cluster id is `cc-<kind>_<its own card>`); Refresh on
              `w462` and `result-w462` (auth_failed, each card offers Rejoin); `result-w462`'s Rejoin opened, nothing
              typed, the page repainted under the dialog, Cancel pressed, `document.activeElement` recorded; `w462`'s
              Rotate opened, `walk-draft-462` typed, the page left alone past the minute's repaint, the field read
              back on `w462`'s card (its length and whether it equals the draft), then the panel closed.
    walk.py after
        a fresh login once the grant is removed: the tier the dashboard now answers.

A route guard lets reads through and only one write: POST …/<throwaway>/refresh. Everything else (Overwrite, Delete,
Rejoin's submit) is aborted and fails the walk. No other card is clicked. The login password comes from the
environment only (GSD_UI_PASSWORD) and is never printed. Exits non-zero on a page error, a visible "Dashboard API
error", a blocked request or a failed expectation."""
import json, os, pathlib, re, sys, time
from playwright.sync_api import sync_playwright

BASE = os.environ.get("GSD_BASE", "https://group-sync-dashboard.apps-crc.testing")
USER = "developer"
HERE = pathlib.Path(__file__).resolve().parent
SHOTS = HERE.parent / "screenshots"
WIDTHS = [(1280, 900), (768, 1024), (375, 812)]
NARROW = (320, 812)                          # #473 alone
THROWAWAY = ("w462", "result-w462", "constructor")
REFUSAL = "gsd-cluster-mock-refusal"
DRAFT = "walk-draft-462"                     # not a credential for anything; typed into a type=password field
FLEET_NAME = "[data-cc-fleet] .v > .mono"    # masked in every screenshot
failures: list[str] = []
blocked: list[str] = []


def utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def say(tag: str, value) -> None:
    print(f"{utc()} {tag:40s}: {value if isinstance(value, str) else json.dumps(value)}", flush=True)


def expect(what: str, ok: bool, detail) -> None:
    say(f"{'PASS' if ok else 'FAIL'} {what}", detail)
    if not ok:
        failures.append(what)


def guard(route) -> None:
    req = route.request
    path = req.url.split("?")[0]
    if req.method == "GET" or (req.method == "POST"
                               and any(path.endswith(f"/api/clusterconfigs/{n}/refresh") for n in THROWAWAY)):
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


def whoami(page) -> dict:
    return page.evaluate("() => ({ user: data.whoami.user, cluster_admin: (data.whoami.visibility || {}).cluster_admin })")


def shot(el, name: str) -> None:
    el.scroll_into_view_if_needed(); el.page.wait_for_timeout(300)
    el.screenshot(path=str(SHOTS / name), mask=[el.page.locator(FLEET_NAME)])
    say("shot", name)


def card(page, cid: str):
    return page.locator(f"#cc-cluster-{cid}")


def text(page, sel: str) -> str | None:
    return page.evaluate("(s) => { const e = document.querySelector(s);"
                         " return e ? e.innerText.replace(/\\s+/g, ' ').trim() : null; }", sel)


def open_clusters(page) -> None:
    page.goto(BASE + "/#page=clusters", wait_until="networkidle")
    page.wait_for_selector("#cc-head", timeout=30_000)
    page.wait_for_selector("[data-cc-cluster]", timeout=30_000)
    # the web fonts swap in and a line break follows the glyph widths: measure once they are in (as #473's test does)
    page.evaluate("() => document.fonts.ready")
    page.wait_for_timeout(1000)


def page_checks(page, w: str, errors: list) -> None:
    sw = page.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")
    expect(f"[{w}] no sideways page scroll (scrollWidth, innerWidth)", sw[0] <= sw[1], sw)
    expect(f"[{w}] no 'Dashboard API error'", page.locator("text=Dashboard API error").count() == 0, None)
    expect(f"[{w}] no uncaught page errors", not errors, errors)


# --- #473 ---------------------------------------------------------------------------------------------------------
FINDING_JS = """(source) => {
  const art = [...document.querySelectorAll('#cc-findings .cc-finding')]
    .find(a => [...a.querySelectorAll('.cc-kv')].some(r => r.querySelector('.k').textContent === 'source'
                                                          && r.querySelector('.v').textContent === source));
  if (!art) return null;
  const row = [...art.querySelectorAll('.cc-kv')].find(r => r.querySelector('.k').textContent === 'detail');
  const k = row.querySelector('.k'), v = row.querySelector('.v'), node = v.firstChild;
  const range = document.createRange(), lines = [];
  let top = null;
  for (let i = 0; i < node.length; i++) {
    range.setStart(node, i); range.setEnd(node, i + 1);
    const rect = range.getClientRects()[0];
    if (!rect) continue;
    if (top === null || Math.abs(rect.top - top) > 2) { lines.push(''); top = rect.top; }
    lines[lines.length - 1] += node.data[i];
  }
  const kr = k.getBoundingClientRect(), vr = v.getBoundingClientRect();
  return { detail: node.data, lines,
           columns: getComputedStyle(row).gridTemplateColumns.split(' ').length,
           grid_template_columns: getComputedStyle(row).gridTemplateColumns,
           label: { left: Math.round(kr.left), right: Math.round(kr.right), top: Math.round(kr.top), bottom: Math.round(kr.bottom) },
           value: { left: Math.round(vr.left), right: Math.round(vr.right), top: Math.round(vr.top), bottom: Math.round(vr.bottom) },
           fonts_in: document.fonts.check('12px "Space Grotesk"') };
}"""


def walk_473(page, w: str, width: int, n: int) -> int:
    f = page.evaluate(FINDING_JS, REFUSAL)
    expect(f"[{w}] #473: the Findings card lists {REFUSAL}", f is not None, f)
    if f is None:
        return n
    say(f"[{w}] #473 detail facts", f)
    lines, detail = f["lines"], f["detail"]
    ends = [sum(map(len, lines[:i])) for i in range(1, len(lines))]
    at = detail.find("insecure=true")
    split_inside_word = [e for e in ends if " " not in detail[e - 1:e + 1]]
    split_inside_token = [e for e in ends if at < e < at + len("insecure=true")]
    expect(f"[{w}] #473: every character read; `insecure=true` in the detail",
           "".join(lines) == detail and at >= 0 and f["fonts_in"], {"lines": len(lines), "fonts_in": f["fonts_in"]})
    expect(f"[{w}] #473: every line ends between words; `insecure=true` never split",
           not split_inside_word and not split_inside_token,
           {"line_ends": ends, "inside_a_word": split_inside_word, "inside_insecure=true": split_inside_token})
    if width < 520:
        expect(f"[{w}] #473: one column, the label above the value",
               f["columns"] == 1 and f["label"]["bottom"] <= f["value"]["top"] + 1,
               {"columns": f["columns"], "label_bottom": f["label"]["bottom"], "value_top": f["value"]["top"]})
    else:
        expect(f"[{w}] #473: two columns, the label beside the value",
               f["columns"] == 2 and f["label"]["right"] <= f["value"]["left"] + 1 and abs(f["label"]["top"] - f["value"]["top"]) <= 2,
               {"columns": f["columns"], "label_right": f["label"]["right"], "value_left": f["value"]["left"],
                "tops": [f["label"]["top"], f["value"]["top"]]})
    art = page.locator("#cc-findings .cc-finding", has_text=REFUSAL)
    shot(art, f"{n:02d}-{w}-473-finding.png"); n += 1
    return n


# --- #467 ---------------------------------------------------------------------------------------------------------
def discovery_counts(evidence: pathlib.Path) -> dict:
    lines = [l for l in evidence.read_text().splitlines() if " discovery cycle=" in l]
    last = lines[-1]
    return {k: int(re.search(rf" {k}=(\d+)", last).group(1)) for k in ("seen", "accepted", "refused")} | {
        "cycle": int(re.search(r" cycle=(\d+)", last).group(1)), "at": last.split(" ", 1)[0]}


def walk_467(page, w: str, n: int, disc: dict) -> int:
    facts = page.evaluate("""() => { const h = document.getElementById('cc-head');
        const row = [...h.querySelectorAll('.cc-kv')].find(x => x.querySelector('.k').textContent === 'discovery');
        const d = data.clusterconfigs;
        return { line: row.querySelector('.v').innerText.replace(/\\s+/g, ' ').trim(),
                 served_from_secret: d.clusters.filter(c => !c.retired && !c.host && String(c.source || '').startsWith('secret:'))
                                               .map(c => c.id),
                 api_findings: (d.findings || []).map(f => [f.secret, f.code]),
                 findings_card: [...document.querySelectorAll('#cc-findings .cc-finding')].map(a => {
                     const kv = (k) => [...a.querySelectorAll('.cc-kv')].find(r => r.querySelector('.k').textContent === k)
                                         .querySelector('.v').textContent;
                     return [kv('source'), kv('code')]; }) }; }""")
    say(f"[{w}] #467 discovery line and sources", facts)
    m = re.match(r"^(\d+) served from (a Secret|Secrets)(?: · (\d+) labelled Secrets? refused \(see Findings\))? · last read ",
                 facts["line"])
    expect(f"[{w}] #467: the line reads `N served from Secrets · M labelled Secret(s) refused (see Findings) · last read …`",
           bool(m), facts["line"])
    if m:
        n_served, m_refused = int(m.group(1)), int(m.group(3) or 0)
        card_secrets = {s for s, _ in facts["findings_card"] if not s.startswith("configmap:") and s != "values"}
        expect(f"[{w}] #467: N = the clusters served from a Secret = discovery's accepted",
               n_served == len(facts["served_from_secret"]) == disc["accepted"],
               {"N": n_served, "served_from_secret": len(facts["served_from_secret"]), "discovery accepted": disc["accepted"]})
        expect(f"[{w}] #467: M = the labelled Secrets on the Findings card = discovery's refused",
               m_refused == len(card_secrets) == disc["refused"],
               {"M": m_refused, "findings card Secrets": sorted(card_secrets), "discovery refused": disc["refused"]})
    shot(page.locator("#cc-head"), f"{n:02d}-{w}-467-header.png"); n += 1
    return n


# --- #462 ---------------------------------------------------------------------------------------------------------
ID_JS = """() => {
  const ids = [...document.querySelectorAll('[id]')].map(e => e.id);
  const seen = new Set(), dup = new Set();
  ids.forEach(i => { if (seen.has(i)) dup.add(i); seen.add(i); });
  const perCard = [], offScheme = [];
  document.querySelectorAll('[data-cc-cluster]').forEach(c => {
    const owner = c.dataset.ccCluster;
    c.querySelectorAll('[id]').forEach(e => {
      const m = /^cc-([a-z-]+)_(.+)$/.exec(e.id);
      perCard.push([e.id, owner]);
      if (!m || m[2] !== owner) offScheme.push([e.id, owner]);
    });
  });
  const oldScheme = ids.filter(i => /^cc-(refresh|refresh-result|rejoin|rejoin-result|rotate|rotate-token|rotate-go|rotate-msg|delete|delete-msg)-/.test(i)
                                    && !i.includes('_'));
  const cards = [...document.querySelectorAll('[data-cc-cluster]')].map(c => [c.id, c.dataset.ccCluster]);
  return { ids: ids.length, duplicates: [...dup], cards: cards.length,
           cards_off_their_id: cards.filter(([id, o]) => id !== 'cc-cluster-' + o),
           per_card_ids: perCard.length, off_scheme: offScheme, old_scheme: oldScheme,
           throwaway_ids: perCard.filter(([, o]) => ['w462', 'result-w462', 'constructor'].includes(o)) };
}"""


def id_check(page, w: str, when: str) -> dict:
    ids = page.evaluate(ID_JS)
    say(f"[{w}] #462 id check {when}", ids)
    expect(f"[{w}] #462 {when}: no duplicate id; every per-cluster id is cc-<kind>_<its own card>",
           not ids["duplicates"] and not ids["off_scheme"] and not ids["old_scheme"] and not ids["cards_off_their_id"],
           {k: ids[k] for k in ("ids", "per_card_ids", "duplicates", "off_scheme", "old_scheme")})
    return ids


def press_refresh(page, cid: str) -> str | None:
    assert cid in THROWAWAY
    page.click(f"#cc-refresh_{cid}")
    page.wait_for_function("(id) => { const r = document.getElementById('cc-refresh-result_' + id);"
                           " return r && !/probing/.test(r.innerText); }", arg=cid, timeout=60_000)
    return text(page, f"#cc-refresh-result_{cid}")


def refused_and_offered(page, w: str, cid: str, line: str | None) -> bool:
    offer = page.locator(f"#cc-cluster-{cid} #cc-rejoin_{cid}")
    ok = bool(re.match(r"^Refresh: auth_failed · ", line or "")) and offer.count() == 1 and offer.inner_text().strip() == "Rejoin…"
    expect(f"[{w}] {cid}: Refresh answers auth_failed and its own card offers Rejoin", ok,
           {"line": line, "rejoin_button": offer.inner_text().strip() if offer.count() else None})
    return ok


def rotate_facts(page, cid: str) -> dict | None:
    """The field's facts, never its value: whether it equals the draft, its length, its type, its card."""
    return page.evaluate("""([cid, draft]) => { const f = document.getElementById('cc-rotate-token_' + cid);
        if (!f) return null;
        const c = f.closest('[data-cc-cluster]');
        return { id: f.id, card: c ? c.dataset.ccCluster : null, equals_draft: f.value === draft, length: f.value.length,
                 type: f.type, label_for_it: f.labels.length, marker: f.dataset.walkMark || null }; }""", [cid, DRAFT])


def walk_462(page, w: str, n: int, api_requests: list) -> int:
    id_check(page, w, "idle")
    for cid in ("w462", "result-w462"):
        line = press_refresh(page, cid)
        say(f"[{w}] {cid} refresh answered", line)
        refused_and_offered(page, w, cid, line)
    ids = id_check(page, w, "after both Refresh answers")
    say(f"[{w}] #462 ids on the pair's cards", [i for i in ids["throwaway_ids"] if i[1] != "constructor"])
    shot(card(page, "w462"), f"{n:02d}-{w}-462-w462-refused.png"); n += 1
    shot(card(page, "result-w462"), f"{n:02d}-{w}-462-result-w462-refused.png"); n += 1

    # result-w462's Rejoin: opened, nothing typed, the page repainted under it, Cancel
    page.click("#cc-rejoin_result-w462")
    page.wait_for_function("() => document.getElementById('rejoin-dialog').open", timeout=10_000)
    opened = page.evaluate("""() => { const d = document.getElementById('rejoin-dialog');
        return { open: d.open, cluster: d.dataset.cluster, username_length: document.getElementById('rejoin-username').value.length,
                 password_length: document.getElementById('rejoin-password').value.length }; }""")
    say(f"[{w}] Rejoin dialog opened", opened)
    # the repaint #462's fix is for, done the way the PR's test does it: a marker on the button that opened the dialog,
    # the fingerprint cleared, one refresh; the marker's absence proves the button was replaced
    page.evaluate("() => { document.getElementById('cc-rejoin_result-w462').dataset.walkMark = 'opener';"
                  " lastFingerprint = null; return refresh({ auto: true }); }")
    page.wait_for_function("() => { const b = document.getElementById('cc-rejoin_result-w462'); return b && !b.dataset.walkMark; }",
                           timeout=30_000)
    say(f"[{w}] repainted under the dialog", "the opener's node was replaced")
    page.evaluate("() => { window.__walkClosed = false; document.getElementById('rejoin-dialog')"
                  ".addEventListener('close', () => { window.__walkClosed = true; }, { once: true }); }")
    page.click("#rejoin-cancel")
    page.wait_for_function("() => window.__walkClosed && !document.getElementById('rejoin-dialog').open", timeout=10_000)
    focus = page.evaluate("""() => { const a = document.activeElement, c = a && a.closest('[data-cc-cluster]');
        return { active_id: a ? a.id : null, tag: a ? a.tagName : null, data_cc_rejoin: a ? a.dataset.ccRejoin || null : null,
                 card: c ? c.dataset.ccCluster : null, text: a ? a.innerText.trim() : null }; }""")
    say(f"[{w}] document.activeElement after Cancel", focus)
    expect(f"[{w}] #462: nothing typed; after the repaint and Cancel, the focus is result-w462's own Rejoin button",
           opened["open"] and opened["cluster"] == "result-w462" and opened["username_length"] == 0
           and opened["password_length"] == 0 and focus["active_id"] == "cc-rejoin_result-w462"
           and focus["card"] == "result-w462" and focus["data_cc_rejoin"] == "result-w462", focus)
    shot(card(page, "result-w462"), f"{n:02d}-{w}-462-result-w462-focus-after-cancel.png"); n += 1

    # w462's Rotate: the draft survives the minute's repaint on w462's own card
    page.click("#cc-rotate_w462")
    page.locator("#cc-rotate-token_w462").wait_for(timeout=10_000)
    page.fill("#cc-rotate-token_w462", DRAFT)
    typed = rotate_facts(page, "w462")
    say(f"[{w}] typed into w462's Rotate", typed)
    expect(f"[{w}] #462: typed {len(DRAFT)} characters into w462's own field, masked",
           typed["card"] == "w462" and typed["equals_draft"] and typed["length"] == len(DRAFT)
           and typed["type"] == "password" and typed["label_for_it"] == 1, typed)
    page.evaluate("() => { document.getElementById('cc-rotate-token_w462').dataset.walkMark = 'before'; }")
    before_n, t0 = len(api_requests), time.time()
    say(f"[{w}] leaving the page alone", "from " + utc())
    waited, after = 0, None
    for _ in range(3):   # the timer skips the repaint when the payload is unchanged: up to three ticks
        page.wait_for_timeout(65_000); waited += 65
        after = rotate_facts(page, "w462")
        if after is None or after["marker"] is None:
            break
    polls = [s for (t, s) in api_requests[before_n:] if t >= t0]
    say(f"[{w}] after {waited} s: GET /api/clusterconfigs", polls)
    say(f"[{w}] after {waited} s: w462's field", after)
    other = page.evaluate("() => [...document.querySelectorAll('.cc-panel input')].map(i => [i.id, i.closest('[data-cc-cluster]').dataset.ccCluster])")
    say(f"[{w}] Rotate fields on the page", other)
    expect(f"[{w}] #462: after the repaint the field is a new node on w462's card holding the draft",
           bool(after) and after["marker"] is None and after["card"] == "w462" and after["equals_draft"]
           and after["length"] == len(DRAFT) and after["type"] == "password" and len(polls) >= 1
           and other == [["cc-rotate-token_w462", "w462"]],
           {"repainted": bool(after) and after["marker"] is None, "card": after and after["card"],
            "equals_draft": bool(after) and after["equals_draft"], "length": after and after["length"],
            "polls": polls, "waited_s": waited, "rotate fields": other})
    shot(card(page, "w462"), f"{n:02d}-{w}-462-w462-rotate-after-repaint.png"); n += 1
    page.click("#cc-rotate_w462")                     # close: the draft belongs to the open panel
    page.wait_for_timeout(300)
    expect(f"[{w}] w462's Rotate closed", rotate_facts(page, "w462") is None, None)
    return n


# --- #459 ---------------------------------------------------------------------------------------------------------
def constructor_facts(page) -> dict:
    return page.evaluate("""() => { const c = document.getElementById('cc-cluster-constructor');
        if (!c) return null;
        const t = c.innerText;
        return { refresh_line: !!document.getElementById('cc-refresh-result_constructor'),
                 rejoin_line: !!document.getElementById('cc-rejoin-result_constructor'),
                 rejoin_button: !!document.getElementById('cc-rejoin_constructor'),
                 text_has_refresh_colon: t.includes('Refresh:'), text_has_rejoin_colon: t.includes('Rejoin:'),
                 text_has_rejoin_button: t.includes('Rejoin…'),
                 refresh_button: (document.getElementById('cc-refresh_constructor') || {}).innerText || null }; }""")


def walk_459_idle(page, w: str, n: int) -> int:
    f = constructor_facts(page)
    say(f"[{w}] #459 constructor, idle", f)
    expect(f"[{w}] #459: idle, no Refresh: line, no Rejoin: line, no Rejoin button",
           f is not None and not any(f[k] for k in ("refresh_line", "rejoin_line", "rejoin_button", "text_has_refresh_colon",
                                                    "text_has_rejoin_colon", "text_has_rejoin_button"))
           and f["refresh_button"] == "Refresh", f)
    shot(card(page, "constructor"), f"{n:02d}-{w}-459-constructor-idle.png"); n += 1
    return n


def walk_459_refreshed(page, w: str, n: int) -> int:
    line = press_refresh(page, "constructor")
    say(f"[{w}] constructor refresh answered", line)
    refused_and_offered(page, w, "constructor", line)
    f = constructor_facts(page)
    say(f"[{w}] #459 constructor, refreshed", f)
    expect(f"[{w}] #459: after Refresh, a Refresh: line and a Rejoin button, no Rejoin: line",
           f["refresh_line"] and f["rejoin_button"] and not f["rejoin_line"] and not f["text_has_rejoin_colon"], f)
    shot(card(page, "constructor"), f"{n:02d}-{w}-459-constructor-refreshed.png"); n += 1
    return n


def walk_width(ctx, width: int, height: int, n: int, disc: dict, api_requests: list) -> int:
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("response", lambda r: api_requests.append((time.time(), r.status))
            if r.url.split("?")[0].endswith("/api/clusterconfigs") and r.request.method == "GET" else None)
    page.set_viewport_size({"width": width, "height": height})
    open_clusters(page)
    w = f"{width}"
    listed = page.evaluate("(ids) => ids.filter(i => document.getElementById('cc-cluster-' + i))", list(THROWAWAY))
    expect(f"[{w}] the three throwaway cards are listed", listed == list(THROWAWAY), listed)
    if (width, height) == NARROW:
        n = walk_473(page, w, width, n)
    else:
        n = walk_459_idle(page, w, n)          # first, before any Refresh on this page
        n = walk_473(page, w, width, n)
        n = walk_467(page, w, n, disc)
        n = walk_462(page, w, n, api_requests)
        n = walk_459_refreshed(page, w, n)
        ids = id_check(page, w, "at the end, all three refreshed")
        say(f"[{w}] #462 ids on the throwaway cards", ids["throwaway_ids"])
    page_checks(page, w, errors)
    page.close()
    return n


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in ("walk", "after") or (mode == "walk" and len(sys.argv) != 3):
        sys.exit("usage: walk.py walk <discovery evidence> | walk.py after")
    disc = discovery_counts(pathlib.Path(sys.argv[2])) if mode == "walk" else {}
    if disc:
        say("discovery, the last cycle line", disc)
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 900})
        ctx.route(re.compile(r".*/api/clusterconfigs.*"), guard)
        page = ctx.new_page()
        login(page)
        who = whoami(page)
        say("whoami", who)
        status = page.evaluate("async () => { const s = {}; for (const u of ['/api/whoami', '/api/clusterconfigs'])"
                               " s[u] = (await fetch(u, { credentials: 'same-origin' })).status; return s; }")
        say("status", status)
        if mode == "after":
            tabs = page.evaluate("() => [...document.querySelectorAll('button.tab')].map(b => b.textContent.trim())")
            has = any("Cluster Configurations" in t for t in tabs)
            expect("after the grant's removal: no cluster-admin tier, the tab absent, /api/clusterconfigs 403",
                   who["cluster_admin"] is False and not has and status["/api/clusterconfigs"] == 403,
                   {"cluster_admin": who["cluster_admin"], "tab": has, "status": status["/api/clusterconfigs"]})
        else:
            expect("developer holds the cluster-admin tier for the walk",
                   who["cluster_admin"] is True and status["/api/clusterconfigs"] == 200, who)
            page.close()
            if not failures:
                n, api_requests = 1, []
                for width, height in [*WIDTHS, NARROW]:
                    n = walk_width(ctx, width, height, n, disc, api_requests)
        br.close()
    expect("the route guard blocked no request", not blocked, blocked)
    say("failures", failures)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
