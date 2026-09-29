#!/usr/bin/env python3
"""#478 on the deployed dashboard (application 1.17.0), as `developer`, at 1280 and 375 px.

    walk.py granted     developer holds the cluster-admin tier (scripts/grant.yaml):
        C5    the stale link: `#page=overview&cluster=<id>` for zzz-unknown, constructor and toString, each on a fresh
              load and once more by setting `location.hash` after a good Home load. Recorded per case: the scope
              pill's text and class, whether #main says "No cluster by that id is configured", narrowedReader(),
              scopeFor(data.whoami, <id>), and the page errors. The three ids must read the same.
        form  Cluster Configurations → Add cluster: name walk-478, server https://api.crc.testing:6443, the token
              string `walk-478-not-a-token` (no server issued it), the CA mode "use the trusted bundle", then the
              labels constructor=c and __proto__=p. Recorded: both chips, Object.getPrototypeOf(labels) === null, the
              YAML twin's label lines. At 1280 px only, Create is pressed ONCE: the message, and the POST's status
              and detail from a response listener; then `capture.sh secret aftercreate`. At 375 px the form is
              filled and read, and Create is not pressed.
        ns    the namespace list, one labelled namespace's page, one unlabelled namespace's page, and the lookup with
              a real label value typed into its box (`q` is not a position key, index.html POSITION_KEYS): each
              label cell against the API's own labels (the value where the namespace has the key, `—` where it
              does not); `data.namespaces.label_keys`.
    walk.py ungranted   after the grant is removed and 70 s have passed: the tier, then C5 again.
    walk.py granted-rerun | ungranted-rerun   the second pass (walk.sh rerun), after the first read the hash-edit
        cases before their repaint: C5 at both widths again, and the form (Create NOT pressed) and the namespace
        pages at 375 px, which the first pass never reached.

A route guard on the dashboard's /api/ lets every GET through and ONE POST /api/clusterconfigs, and that one only
when its JSON body's labels carry `__proto__` (so a build that dropped the key could not write the Secret). Every
other write is aborted and fails the walk. The login password comes from the environment only (GSD_UI_PASSWORD) and
is never printed; the request body (it holds the token string) is never printed. Exits non-zero on a failed
expectation."""
import json, os, pathlib, re, subprocess, sys, time
from playwright.sync_api import sync_playwright

BASE = os.environ.get("GSD_BASE", "https://group-sync-dashboard.apps-crc.testing")
USER = "developer"
HERE = pathlib.Path(__file__).resolve().parent
SHOTS = HERE.parent / "screenshots"
WIDTHS = [(1280, 900), (375, 812)]
STALE_IDS = ("zzz-unknown", "constructor", "toString")
FORM = {"name": "walk-478", "server": "https://api.crc.testing:6443", "token": "walk-478-not-a-token"}
LABELS = [("constructor", "c"), ("__proto__", "p")]
FLEET_NAME = "[data-cc-fleet] .v > .mono"    # masked in every screenshot
failures: list[str] = []
blocked: list[str] = []
posts: list[dict] = []


def utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def say(tag: str, value) -> None:
    print(f"{utc()} {tag:44s}: {value if isinstance(value, str) else json.dumps(value)}", flush=True)


def expect(what: str, ok: bool, detail) -> None:
    say(f"{'PASS' if ok else 'FAIL'} {what}", detail)
    if not ok:
        failures.append(what)


def guard(route) -> None:
    req = route.request
    path = req.url.split("?")[0]
    if req.method in ("GET", "HEAD"):
        route.continue_()
        return
    if req.method == "POST" and path.endswith("/api/clusterconfigs") and not posts:
        try:
            labels = (req.post_data_json or {}).get("labels") or {}
        except Exception:                                  # a body that is not JSON is not this form's
            labels = {}
        keys = list(labels)
        posts.append({"at": utc(), "label_keys": keys})
        if "__proto__" in keys:
            say("guard: the one Create POST, label keys", keys)
            route.continue_()
            return
        say("guard: Create POST WITHOUT __proto__ aborted, label keys", keys)
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


def tier(page) -> dict:
    return page.evaluate("""async () => { const v = data.whoami.visibility || {};
        return { user: data.whoami.user, scope: v.scope, cluster_admin: v.cluster_admin,
                 visibility_clusters: v.clusters ? Object.keys(v.clusters) : null,
                 clusterconfigs_status: (await fetch('/api/clusterconfigs', { credentials: 'same-origin' })).status }; }""")


def shot(page, name: str, el=None) -> None:
    mask = [page.locator(FLEET_NAME)]
    if el is None:
        page.screenshot(path=str(SHOTS / name), mask=mask)
    else:
        el.scroll_into_view_if_needed(); page.wait_for_timeout(300)
        el.screenshot(path=str(SHOTS / name), mask=mask)
    say("shot", name)


def settle(page) -> None:
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1500)


def new_page(ctx, errors: list):
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    return page


# --- C5: the stale link --------------------------------------------------------------------------------------------
STALE_JS = """(id) => {
  const pill = document.getElementById('scope-pill'), main = document.getElementById('main');
  const vis = data.whoami && data.whoami.visibility;
  const h2 = main && main.querySelector('h2');
  return { hash: location.hash, view_page: view.page, view_cluster: view.cluster,
           pill_text: pill ? pill.textContent : null, pill_class: pill ? pill.className : null,
           pill_hidden: pill ? pill.hidden : null,
           no_cluster_note: !!main && main.innerText.includes('No cluster by that id is configured'),
           main_h2: h2 ? h2.textContent.trim() : null,
           narrowedReader: narrowedReader(), scopeFor: scopeFor(data.whoami, id),
           whoami_scope: vis ? vis.scope : null,
           own_key_in_whoami_clusters: !!(vis && vis.clusters) && Object.prototype.hasOwnProperty.call(vis.clusters, id),
           dashboard_api_error: document.body.innerText.includes('Dashboard API error') };
}"""
SAME = ("pill_text", "pill_class", "pill_hidden", "no_cluster_note", "narrowedReader", "scopeFor")


def stale_case(ctx, w: str, phase: str, cid: str, how: str, n: int) -> tuple[dict, int]:
    errors: list[str] = []
    page = new_page(ctx, errors)
    target = f"#page=overview&cluster={cid}"
    if how == "fresh":
        page.goto(BASE + "/" + target, wait_until="networkidle")
    else:
        page.goto(BASE + "/", wait_until="networkidle")
        page.wait_for_function("() => data.whoami && data.whoami.authenticated && view.page === 'home'", timeout=30_000)
        settle(page)
        home = page.evaluate("() => ({ view_page: view.page, view_cluster: view.cluster, main_h2: (document.querySelector('#main h2') || {}).textContent || null,"
                             " pill_text: document.getElementById('scope-pill').textContent,"
                             " dashboard_api_error: document.body.innerText.includes('Dashboard API error') })")
        say(f"[{phase} {w}] {cid} hash: the Home load first", home | {"page_errors": list(errors)})
        expect(f"[{phase} {w}] {cid} hash: a good Home load first",
               home["view_page"] == "home" and not home["dashboard_api_error"] and not errors, home)
        # the Home page's first card is marked, then the hash is set: the record is taken only once that card has
        # been replaced by a paint and #main is no longer `stale` (the refresh a hash edit starts took up to ~4 s
        # on the lab; the first run read #main after 1.5 s, still showing Home — evidence/walk-granted.txt)
        page.evaluate("(h) => { document.querySelector('#main > *').dataset.walkMark = 'home'; location.hash = h; }", target)
    page.wait_for_function("(id) => data.whoami && data.whoami.authenticated && view.page === 'overview' && view.cluster === id"
                           " && !document.querySelector('#main [data-walk-mark]')"
                           " && !document.getElementById('main').classList.contains('stale')"
                           " && document.getElementById('main').innerText.trim().length > 0", arg=cid, timeout=30_000)
    settle(page)
    f = page.evaluate(STALE_JS, cid) | {"page_errors": list(errors)}
    say(f"[{phase} {w}] C5 {cid} ({how})", f)
    shot(page, f"{n:02d}-{phase}-{w}-c5-{cid}-{how}.png"); n += 1
    page.close()
    return f, n


def walk_c5(ctx, w: str, phase: str, n: int, expect_scope: str) -> int:
    seen: dict[str, dict] = {}
    for how in ("fresh", "hash"):
        for cid in STALE_IDS:
            f, n = stale_case(ctx, w, phase, cid, how, n)
            seen[f"{cid}/{how}"] = f
            expect(f"[{phase} {w}] C5 {cid} ({how}): no page error, no 'Dashboard API error', the id not in whoami's clusters",
                   not f["page_errors"] and not f["dashboard_api_error"] and not f["own_key_in_whoami_clusters"],
                   {k: f[k] for k in ("page_errors", "dashboard_api_error", "own_key_in_whoami_clusters")})
    for how in ("fresh", "hash"):
        base = {k: seen[f"zzz-unknown/{how}"][k] for k in SAME}
        differ = {c: {k: seen[f"{c}/{how}"][k] for k in SAME if seen[f"{c}/{how}"][k] != base[k]} for c in STALE_IDS}
        differ = {c: d for c, d in differ.items() if d}
        expect(f"[{phase} {w}] C5 ({how}): the three ids read the same",
               not differ and base["scopeFor"] == expect_scope, {"reading": base, "differs": differ})
    fresh = {k: seen["zzz-unknown/fresh"][k] for k in SAME}
    hashed = {k: seen["zzz-unknown/hash"][k] for k in SAME}
    say(f"[{phase} {w}] C5: a fresh load and a hash edit read the same", fresh == hashed)
    return n


# --- the Add-cluster form ------------------------------------------------------------------------------------------
FORM_JS = """() => {
  const f = view.clusterForm;
  const yaml = (document.getElementById('cc-yaml') || {}).textContent || '';
  const labelsBlock = yaml.split('\\n').filter((l) => /^    "/.test(l));
  return { chips: [...document.querySelectorAll('#cc-label-chips .cc-chip')].map((c) => c.firstChild.textContent.trim()),
           proto_is_null: Object.getPrototypeOf(f.labels) === null,
           keys: Object.keys(f.labels),
           own___proto__: Object.prototype.hasOwnProperty.call(f.labels, '__proto__'),
           body_label_keys: Object.keys(JSON.parse(JSON.stringify(ccBody().labels))),
           yaml_label_lines: labelsBlock,
           ca_mode: f.caMode, name: f.name, server: f.server, token_length: f.token.length,
           create_button: !!document.getElementById('cc-create'),
           msg: (document.getElementById('cc-form-msg') || {}).textContent || '' };
}"""


def walk_form(ctx, w: str, n: int, press_create: bool, phase: str) -> int:
    errors: list[str] = []
    page = new_page(ctx, errors)
    page.goto(BASE + "/#page=clusters", wait_until="networkidle")
    page.wait_for_selector("#cc-add #cc-form", timeout=30_000)
    settle(page)
    page.fill("#cc-name", FORM["name"])
    page.fill("#cc-server", FORM["server"])
    page.fill("#cc-token", FORM["token"])
    # "use the trusted bundle": the default, paste PEM, with no PEM is refused as ca-data-invalid BEFORE the labels
    # are read (writer.validate's order), and this row is about the label refusal
    page.check("#cc-ca-trustedBundle")
    for k, v in LABELS:
        page.fill("#cc-label-key", k)
        page.fill("#cc-label-val", v)
        page.click("#cc-label-add")
        page.wait_for_timeout(300)
    f = page.evaluate(FORM_JS)
    say(f"[{w}] form after the two labels", f)
    expect(f"[{w}] form: both chips shown",
           f["chips"] == ["constructor=c", "__proto__=p"], f["chips"])
    expect(f"[{w}] form: Object.getPrototypeOf(view.clusterForm.labels) === null; keys constructor, __proto__",
           f["proto_is_null"] and f["keys"] == ["constructor", "__proto__"] and f["own___proto__"]
           and f["body_label_keys"] == ["constructor", "__proto__"],
           {k: f[k] for k in ("proto_is_null", "keys", "own___proto__", "body_label_keys")})
    expect(f"[{w}] form: the YAML twin lists both keys",
           '    "constructor": "c"' in f["yaml_label_lines"] and '    "__proto__": "p"' in f["yaml_label_lines"],
           f["yaml_label_lines"])
    expect(f"[{w}] form: filled as intended, Create offered",
           f["ca_mode"] == "trustedBundle" and f["name"] == FORM["name"] and f["server"] == FORM["server"]
           and f["token_length"] == len(FORM["token"]) and f["create_button"],
           {k: f[k] for k in ("ca_mode", "name", "server", "token_length", "create_button")})
    shot(page, f"{n:02d}-{phase}-{w}-form-two-labels.png", page.locator("#cc-add")); n += 1
    if press_create:
        ok_to_press = (f["own___proto__"] and "__proto__" in f["body_label_keys"] and not posts)
        expect(f"[{w}] form: safe to press Create (the body carries __proto__, no POST sent yet)", ok_to_press, None)
        if ok_to_press:
            with page.expect_response(lambda r: r.request.method == "POST"
                                      and r.url.split("?")[0].endswith("/api/clusterconfigs"), timeout=30_000) as info:
                page.click("#cc-create")
            resp = info.value
            try:
                detail = resp.json().get("detail")
            except Exception:
                detail = None
            page.wait_for_function("() => { const m = document.getElementById('cc-form-msg');"
                                   " return m && m.textContent && m.textContent !== 'Creating…'; }", timeout=30_000)
            settle(page)
            after = page.evaluate(FORM_JS)
            say(f"[{w}] Create: the POST's status and detail", {"status": resp.status, "detail": detail})
            say(f"[{w}] Create: the form afterwards", {k: after[k] for k in ("msg", "chips", "keys", "name")})
            expect(f"[{w}] Create: 422, label-invalid naming __proto__, the same sentence on the form",
                   resp.status == 422 and isinstance(detail, str) and detail.startswith("label-invalid: ")
                   and "'__proto__'" in detail and after["msg"] == detail,
                   {"status": resp.status, "detail": detail, "msg": after["msg"]})
            shot(page, f"{n:02d}-{phase}-{w}-form-create-refused.png", page.locator("#cc-add")); n += 1
            r = subprocess.run(["bash", str(HERE / "capture.sh"), "secret", "aftercreate"], capture_output=True, text=True)
            ev = (HERE.parent / "evidence" / "aftercreate-secret.txt").read_text()
            say("capture.sh secret aftercreate", ev.strip().replace("\n", " | "))
            expect("no Secret gsd-cluster-walk-478 after the Create", r.returncode == 0 and "NotFound" in ev, None)
    expect(f"[{w}] form: no page error, no 'Dashboard API error'",
           not errors and page.locator("text=Dashboard API error").count() == 0, errors)
    page.close()
    return n


# --- the namespace pages -------------------------------------------------------------------------------------------
LIST_JS = """() => {
  const d = data.namespaces, keys = d.label_keys || [];
  const byName = new Map((d.namespaces || []).map((n) => [n.name, n.labels || {}]));
  const own = (l, k) => Object.prototype.hasOwnProperty.call(l, k) ? l[k] : undefined;
  const rows = [...document.querySelectorAll('#main tr.rowlink[data-ns]')].filter((r) => r.offsetParent !== null);
  const bad = [], shown = [];
  rows.forEach((r) => {
    const name = r.dataset.ns, labels = byName.get(name) || {};
    const cells = [...r.querySelectorAll('td')].slice(1, 1 + keys.length).map((td) => td.textContent.trim());
    const want = keys.map((k) => own(labels, k) || '—');
    shown.push([name, cells]);
    if (JSON.stringify(cells) !== JSON.stringify(want)) bad.push({ name, cells, want });
  });
  const table = rows.length ? rows[0].closest('table') : null;
  const heads = table ? [...table.querySelectorAll('thead th')].map((th) => th.textContent.trim()) : [];
  return { label_keys: keys, namespaces: (d.namespaces || []).length, scope: d.scope, rows: rows.length,
           rows_with_a_value: shown.filter(([, c]) => c.some((x) => x !== '—')).length,
           rows_all_dash: shown.filter(([, c]) => c.every((x) => x === '—')).length,
           mismatches: bad, first_rows: shown.slice(0, 6), headers: heads.slice(0, 2 + keys.length),
           function_or_native_on_page: /function Object|native code/.test(document.getElementById('main').innerText) };
}"""


def pick_namespaces(page) -> dict:
    return page.evaluate("""() => {
      const d = data.namespaces, keys = d.label_keys || [];
      const own = (l, k) => Object.prototype.hasOwnProperty.call(l || {}, k) && l[k];
      const withV = (d.namespaces || []).filter((n) => keys.some((k) => own(n.labels, k)));
      const without = (d.namespaces || []).filter((n) => !keys.some((k) => own(n.labels, k)));
      const lab = withV.sort((a, b) => a.name.localeCompare(b.name))[0];
      const k = lab ? keys.find((kk) => own(lab.labels, kk)) : null;
      return { labelled: lab ? lab.name : null, key: k, value: lab ? lab.labels[k] : null,
               unlabelled: without.length ? without.sort((a, b) => a.name.localeCompare(b.name))[0].name : null,
               with_a_value: withV.length, without_any: without.length }; }""")


DETAIL_JS = """() => {
  const d = data.ns, keys = (d && d.label_keys) || [];
  const labels = (d && d.labels) || {};
  const own = (k) => Object.prototype.hasOwnProperty.call(labels, k) ? labels[k] : undefined;
  const kpis = [...document.querySelectorAll('#main .kpis .kpi')].slice(0, keys.length)
    .map((x) => [x.querySelector('.label').textContent.trim(), x.querySelector('.value').textContent.trim()]);
  const want = keys.map((k) => [k.split('/').pop(), own(k) || '— none —']);
  const note = [...document.querySelectorAll('#main *')].map((e) => e.childNodes.length && e.textContent)
    .find((t) => t && /^(Labelled |Carries none of the captured labels)/.test(t.trim()));
  return { ns: d && d.name, label_keys: keys, labels_for_keys: Object.fromEntries(keys.map((k) => [k, own(k) ?? null])),
           kpis, want, match: JSON.stringify(kpis) === JSON.stringify(want),
           labelled_note: note ? note.trim().replace(/\\s+/g, ' ') : null,
           function_or_native_on_page: /function Object|native code/.test(document.getElementById('main').innerText) };
}"""


LOOKUP_JS = """(q) => {
  const keys = (data.namespaces && data.namespaces.label_keys) || [];
  const byName = new Map(((data.namespaces && data.namespaces.namespaces) || []).map((n) => [n.name, n.labels || {}]));
  const own = (l, k) => Object.prototype.hasOwnProperty.call(l, k) ? l[k] : undefined;
  const rows = [...document.querySelectorAll('#main tr.rowlink[data-ns]')];
  const got = rows.map((r) => [r.dataset.ns, [...r.querySelectorAll('td')].slice(1, 1 + keys.length).map((td) => td.textContent.trim())]);
  const bad = got.filter(([n, c]) => JSON.stringify(c) !== JSON.stringify(keys.map((k) => own(byName.get(n) || {}, k) || '—')));
  const h3 = [...document.querySelectorAll('#main h3')].map((h) => h.textContent.trim().replace(/\\s+/g, ' '));
  return { q, view_lookupSearch: view.lookupSearch, sections: h3, namespace_rows: got, mismatches: bad,
           function_or_native_on_page: /function Object|native code/.test(document.getElementById('main').innerText) };
}"""


def walk_ns(ctx, w: str, n: int, phase: str) -> int:
    errors: list[str] = []
    page = new_page(ctx, errors)
    page.goto(BASE + "/#page=nsaudit", wait_until="networkidle")
    page.wait_for_function("() => data.namespaces && data.namespaces.namespaces", timeout=30_000)
    settle(page)
    fold = page.locator("#ns-index-fold")
    if fold.count() and fold.get_attribute("aria-expanded") == "false":
        fold.click(); page.wait_for_timeout(500)
    pick = pick_namespaces(page)
    say(f"[{w}] ns: the picks", pick)
    lst = page.evaluate(LIST_JS)
    say(f"[{w}] ns list", lst)
    expect(f"[{w}] ns list: every label cell is the API's own value or —; no function source",
           lst["rows"] > 0 and not lst["mismatches"] and not lst["function_or_native_on_page"] and lst["label_keys"],
           {k: lst[k] for k in ("label_keys", "rows", "rows_with_a_value", "rows_all_dash", "mismatches")})
    table = page.locator("#main table").first
    shot(page, f"{n:02d}-{phase}-{w}-ns-list.png", table if table.count() else None); n += 1
    for which in ("labelled", "unlabelled"):
        name = pick[which]
        if not name:
            expect(f"[{w}] ns detail: a {which} namespace exists", False, pick); continue
        page.evaluate("(h) => { location.hash = h; }", f"#page=nsaudit&ns={name}")
        page.wait_for_function("(n) => data.ns && data.ns.name === n", arg=name, timeout=30_000)
        settle(page)
        det = page.evaluate(DETAIL_JS)
        say(f"[{w}] ns detail {which}", det)
        expect(f"[{w}] ns detail ({which} {name}): the label KPIs read the API's own value or '— none —'",
               det["match"] and not det["function_or_native_on_page"], {k: det[k] for k in ("kpis", "want", "labelled_note")})
        shot(page, f"{n:02d}-{phase}-{w}-ns-detail-{which}.png"); n += 1
    # the lookup: typed into its box (the box is the query; `q` in the hash is not a position key)
    page.evaluate("(h) => { location.hash = h; }", "#page=lookup")
    page.wait_for_selector("#f-lookup-search", timeout=30_000)
    page.fill("#f-lookup-search", pick["value"])
    page.wait_for_timeout(1200)
    lk = page.evaluate(LOOKUP_JS, pick["value"])
    say(f"[{w}] lookup", lk)
    names = [r[0] for r in lk["namespace_rows"]]
    expect(f"[{w}] lookup `{pick['value']}`: finds {pick['labelled']}; each label cell the own value or —",
           pick["labelled"] in names and not lk["mismatches"] and not lk["function_or_native_on_page"],
           {"found": pick["labelled"] in names, "namespace_rows": len(names), "mismatches": lk["mismatches"]})
    shot(page, f"{n:02d}-{phase}-{w}-lookup.png"); n += 1
    expect(f"[{w}] ns pages: no page error, no 'Dashboard API error'",
           not errors and page.locator("text=Dashboard API error").count() == 0, errors)
    page.close()
    return n


def main() -> None:
    phase = sys.argv[1] if len(sys.argv) > 1 else ""
    if phase not in ("granted", "granted-rerun", "ungranted", "ungranted-rerun"):
        sys.exit("usage: walk.py granted | granted-rerun | ungranted | ungranted-rerun")
    # granted-rerun (added after the first run): the stale link at both widths with the repaint wait, and the form
    # and the namespace pages at 375 px, which the first run never reached. The form is filled and read, and
    # Create is NOT pressed: the first run pressed it once (evidence/walk-granted.txt), and that is the only press.
    n = {"granted": 1, "granted-rerun": 61, "ungranted": 41, "ungranted-rerun": 101}[phase]
    granted = phase.startswith("granted")
    with sync_playwright() as p:
        br = p.chromium.launch()
        for width, height in WIDTHS:
            w = str(width)
            ctx = br.new_context(ignore_https_errors=True, viewport={"width": width, "height": height})
            ctx.route(re.compile(r"^" + re.escape(BASE) + r"/api/.*"), guard)
            page = ctx.new_page()
            login(page)
            t = tier(page)
            say(f"[{phase} {w}] whoami", t)
            if granted:
                expect(f"[{phase} {w}] developer holds the cluster-admin tier: scope all, /api/clusterconfigs 200",
                       t["cluster_admin"] is True and t["scope"] == "all" and t["clusterconfigs_status"] == 200, t)
            else:
                expect(f"[{phase} {w}] developer has no cluster-admin tier: /api/clusterconfigs 403",
                       t["cluster_admin"] is False and t["clusterconfigs_status"] == 403, t)
            page.close()
            if failures:                                   # the tier is not what this phase needs: stop
                break
            n = walk_c5(ctx, w, phase, n, "all" if granted else t["scope"])
            if phase == "granted" or (phase == "granted-rerun" and width == 375):
                n = walk_form(ctx, w, n, press_create=(phase == "granted" and width == 1280), phase=phase)
                n = walk_ns(ctx, w, n, phase=phase)
            ctx.close()
        br.close()
    expect("the route guard blocked no request", not blocked, blocked)
    want = 1 if phase == "granted" else 0
    expect(f"Create POSTs sent in this phase: {want}", len(posts) == want, posts)
    say("failures", failures)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
