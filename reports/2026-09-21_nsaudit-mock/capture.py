#!/usr/bin/env python3
"""Capture STEP 1 of the Namespace audit redesign: what the LIVE page holds today.

Drives the deployed dashboard (`https://group-sync-dashboard.apps-crc.testing`, oauth-proxy,
kubeadmin) and reads every KPI, column, filter, note, badge, empty state, export and drill path
off the rendered DOM — plus the API payload each is computed from. Nothing here is typed by
hand: `docs/design/nsaudit-feature-capture.md` quotes these lines. Refuses a page with an
uncaught error. Writes `capture.json` and NN-*.png beside itself."""
import json, os, pathlib, sys
from PIL import Image
from playwright.sync_api import sync_playwright

BASE = os.environ.get("GSD_BASE", "https://group-sync-dashboard.apps-crc.testing")
OUT = pathlib.Path(__file__).resolve().parent
USER, PW = os.environ["GSD_UI_USER"], os.environ["GSD_UI_PASSWORD"]
CLEAN = lambda s: " ".join(s.split())
REC = {}


def rec(key, value):
    REC[key] = value
    print(f"{key:24s}:", json.dumps(value, ensure_ascii=False)[:4000], flush=True)


def login(page, user, pw):
    page.goto(BASE, wait_until="networkidle")
    b = page.locator("button:has-text('Log in with OpenShift')")
    if b.count(): b.first.click(); page.wait_for_load_state("networkidle")
    c = page.locator("a:has-text('developer')")
    if c.count(): c.first.click(); page.wait_for_load_state("networkidle")
    page.wait_for_selector("input[name='username']", timeout=20_000)
    page.fill("input[name='username']", user); page.fill("input[name='password']", pw)
    page.click("button[type='submit'], input[type='submit']"); page.wait_for_load_state("networkidle")
    a = page.locator("input[name='approve']")
    if a.count(): a.first.click(); page.wait_for_load_state("networkidle")
    page.wait_for_selector("button.tab", timeout=30_000)


# A full-page capture of this page is 24,444 px tall at 375 and nobody reads that; the repository's
# report folders run to about 1.5 MB. Captures are cropped to the first MAX_PX, which is the part a
# reviewer looks at. Nothing measured depends on the image: every geometry assertion is computed over
# the whole document in the browser.
MAX_PX = 2400


def crop(path):
    im = Image.open(path)
    tall = im.height > MAX_PX
    if tall:
        im = im.crop((0, 0, im.width, MAX_PX))
    im.save(path, optimize=True, compress_level=9)
    return f"{im.width}x{im.height}" + (" (cropped)" if tall else "")


def shot(page, name, full=False, sel=None):
    page.wait_for_timeout(400)
    if sel: page.locator(sel).screenshot(path=str(OUT / name))
    else: page.screenshot(path=str(OUT / name), full_page=full)
    print("shot                    :", name, crop(OUT / name), flush=True)


def open_audit(page):
    page.goto(BASE + "/#page=nsaudit", wait_until="networkidle")
    page.wait_for_function("() => data.userBindings && data.namespaces", timeout=40_000)
    page.wait_for_timeout(900)


def main():
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 1000})
        page = ctx.new_page(); errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        login(page, USER, PW)
        open_audit(page)

        # ── the shell ────────────────────────────────────────────────────────────────────
        rec("version", page.evaluate("() => data.version && {version: data.version.version, sha: data.version.commit || data.version.sha, features: data.version.features}"))
        rec("tabs", page.evaluate("() => [...document.querySelectorAll('button.tab')].map(b => b.textContent.trim())"))
        rec("shell.controls", page.evaluate("""() => ({
            refresh: !!document.querySelector('#refresh'), logout: !!document.querySelector('#logout'),
            cluster_select: document.querySelector('#f-cluster') ? [...document.querySelectorAll('#f-cluster option')].map(o => o.value) : null,
            cluster_value: document.querySelector('#f-cluster') ? document.querySelector('#f-cluster').value : null,
            appearance: document.querySelector('#pref-mode') ? [...document.querySelectorAll('#pref-mode option')].map(o => o.textContent.trim()) : null,
            palette: document.querySelector('#pref-palette') ? [...document.querySelectorAll('#pref-palette option')].map(o => o.textContent.trim()) : null,
            search_box: document.querySelector('#f-ns-search') ? {id: 'f-ns-search', label: (document.querySelector("label[for='f-ns-search']")||{}).textContent, placeholder: document.querySelector('#f-ns-search').placeholder, title: document.querySelector('#f-ns-search').title} : null,
            export_buttons: [...document.querySelectorAll('.filters button, .filters a')].map(b => b.textContent.trim()).filter(Boolean),
            scope_pill: (document.querySelector('#scope-pill') || {}).textContent,
            build_info: (document.querySelector('#build-info') || {}).textContent, last_refresh: (document.querySelector('#last-refresh') || {}).textContent,
            filters_text: (document.querySelector('.filters') || {}).innerText })"""))
        rec("api.userBindings.envelope", page.evaluate("""() => { const u = data.userBindings; return {
            cluster: u.cluster, scope: u.scope, viewer: u.viewer, note: u.note, namespace: u.namespace,
            total: u.total, limit: u.limit, offset: u.offset, truncated: u.truncated,
            excluded_platform: u.excluded_platform, by_namespace_len: (u.by_namespace||[]).length,
            bindings_len: (u.bindings||[]).length }; }"""))
        rec("api.userBindings.by_namespace", page.evaluate("() => data.userBindings.by_namespace"))
        rec("api.userBindings.bindings", page.evaluate("() => data.userBindings.bindings"))
        rec("api.namespaces.envelope", page.evaluate("""() => { const n = data.namespaces; return {
            scope: n.scope, source: n.source, label_keys: n.label_keys, count: (n.namespaces||[]).length,
            cluster_wide_groups: n.cluster_wide_groups, cluster_wide_grants: n.cluster_wide_grants,
            cluster_wide_path: n.cluster_wide_path }; }"""))
        rec("api.namespaces.rows", page.evaluate("() => data.namespaces.namespaces"))

        # ── the page, card by card ───────────────────────────────────────────────────────
        rec("cards", page.evaluate("() => [...document.querySelectorAll('#main > section.card')].map(s => ((s.querySelector('h2,h3')||{textContent:''}).textContent).replace(/\\s+/g,' ').trim())"))
        rec("card.headings", page.evaluate("() => [...document.querySelectorAll('#main h2, #main h3')].map(h => h.textContent.replace(/\\s+/g,' ').trim())"))
        rec("risk.headline", CLEAN(page.locator(".risk-headline").inner_text()) if page.locator(".risk-headline").count() else None)
        rec("kpis", page.evaluate("""() => [...document.querySelectorAll('#main .kpis .kpi')].map(k => ({
            label: (k.querySelector('.label')||{}).textContent.trim(),
            value: (k.querySelector('.value')||{}).textContent.trim(),
            cls: k.className, value_cls: (k.querySelector('.value')||{}).className }))"""))
        rec("why.items", page.evaluate("""() => [...document.querySelectorAll('.risk-item')].map(i => ({
            head: (i.querySelector('.risk-item-h')||{}).textContent.trim(),
            body: i.textContent.replace((i.querySelector('.risk-item-h')||{textContent:''}).textContent,'').replace(/\\s+/g,' ').trim() }))"""))
        rec("exposure.note", page.evaluate("() => { const n = [...document.querySelectorAll('.filterbar-note')].find(x => /Ranked by/.test(x.textContent)); return n && n.textContent.replace(/\\s+/g,' ').trim(); }"))
        rec("exposure.columns", page.evaluate("""() => [...document.querySelectorAll('table.audit-table thead th')].slice(0,6).map(th => ({
            text: th.textContent.replace(/\\s+/g,' ').trim(), sortable: !!th.querySelector('button'),
            aria_sort: th.getAttribute('aria-sort'), cls: th.className }))"""))
        rec("exposure.rows", page.evaluate("""() => [...document.querySelectorAll('table.audit-table tbody tr')].map(tr => ({
            cls: tr.className, cells: [...tr.children].map(td => td.textContent.replace(/\\s+/g,' ').trim()) }))"""))
        rec("exposure.platform_note", page.evaluate("() => { const n = [...document.querySelectorAll('.filterbar-note')].find(x => /platform identit/.test(x.textContent)); return n && n.textContent.replace(/\\s+/g,' ').trim(); }"))
        rec("runbook", page.evaluate("() => [...document.querySelectorAll('ol.runbook li')].map(li => li.textContent.replace(/\\s+/g,' ').trim())"))
        rec("runbook.goal", page.evaluate("() => { const n = [...document.querySelectorAll('.filterbar-note')].find(x => /Operational goal/.test(x.textContent)); return n && n.textContent.replace(/\\s+/g,' ').trim(); }"))
        rec("grants.disclosure", page.evaluate("""() => { const b = document.querySelector('[data-ns-grants]'); return b && {
            text: b.textContent.replace(/\\s+/g,' ').trim(), expanded: b.getAttribute('aria-expanded'),
            controls: b.getAttribute('aria-controls'), hidden_now: document.querySelector('#every-grant').hasAttribute('hidden') }; }"""))
        rec("grants.note", page.evaluate("() => { const n = [...document.querySelectorAll('.filterbar-note')].find(x => /flat detail/.test(x.textContent)); return n && n.textContent.replace(/\\s+/g,' ').trim(); }"))
        rec("grants.select", page.evaluate("""() => { const s = document.querySelector('#ns-pick'); return s && {
            label: (document.querySelector("label[for='ns-pick']")||{}).textContent,
            value: s.value, options: [...s.options].map(o => o.textContent.replace(/\\s+/g,' ').trim()) }; }"""))
        rec("who.preview", page.evaluate("""() => [...document.querySelectorAll('td.who')].map(td => ({
            names: [...td.querySelectorAll('.who-name')].map(n => n.textContent.trim()),
            more: (td.querySelector('.who-more')||{textContent:null}).textContent }))"""))
        shot(page, "live-01-audit-1280.png", full=True)

        # ── interactions ─────────────────────────────────────────────────────────────────
        more = page.locator(".who-more").first
        if more.count():
            ns_of_more = more.get_attribute("data-who"); more.click(); page.wait_for_timeout(300)
            rec("who.expanded", page.evaluate("""(ns) => { const tr = [...document.querySelectorAll('tr.risk-row')].find(r => r.children[1].textContent.trim() === ns);
                const td = tr && tr.querySelector('td.who'); return td && { ns, names: [...td.querySelectorAll('.who-name')].map(n => n.textContent.trim()),
                toggle: (td.querySelector('.who-more')||{textContent:null}).textContent }; }""", ns_of_more))
            page.locator(".who-more").first.click(); page.wait_for_timeout(250)

        th_people = page.locator("table.audit-table thead th button", has_text="People").first
        if th_people.count():
            th_people.click(); page.wait_for_timeout(350)
            rec("sort.after_people_click", page.evaluate("""() => ({ view: {sort: view.nsSort, dir: view.nsDir},
                aria: [...document.querySelectorAll('table.audit-table thead th')].map(th => th.getAttribute('aria-sort')),
                first_rows: [...document.querySelectorAll('table.audit-table tbody tr')].slice(0,3).map(tr => [...tr.children].map(td => td.textContent.replace(/\\s+/g,' ').trim())),
                reset_button: (document.querySelector('[data-ns-reset]')||{textContent:null}).textContent })"""))
            page.locator("[data-ns-reset]").click(); page.wait_for_timeout(350)
            rec("sort.after_reset", page.evaluate("() => ({ view: {sort: view.nsSort, dir: view.nsDir}, reset_button: !!document.querySelector('[data-ns-reset]') })"))

        page.click("[data-ns-grants]"); page.wait_for_timeout(500)
        rec("grants.expanded", page.evaluate("""() => ({ hidden: document.querySelector('#every-grant').hasAttribute('hidden'),
            button: document.querySelector('[data-ns-grants]').textContent.replace(/\\s+/g,' ').trim(),
            columns: [...document.querySelectorAll('#every-grant table.audit-table thead th')].map(th => th.textContent.replace(/\\s+/g,' ').trim()),
            rows: [...document.querySelectorAll('#every-grant table.audit-table tbody tr')].map(tr => ({ cls: tr.className,
                cells: [...tr.children].map(td => td.textContent.replace(/\\s+/g,' ').trim()) })),
            truncation: (document.querySelector('#every-grant .truncation-note')||{textContent:null}).textContent })"""))
        shot(page, "live-02-every-grant-1280.png", full=True)

        rec("export.controls", page.evaluate("""() => [...document.querySelectorAll('button, a')].filter(b => /CSV|JSON|export/i.test(b.textContent)).map(b => ({
            text: b.textContent.replace(/\\s+/g,' ').trim(), id: b.id, title: b.title, cls: b.className }))"""))
        rec("export.note", page.evaluate("() => { const n = [...document.querySelectorAll('.filters *, #main *')].find(x => /rows?\\b.*(export|served)/i.test(x.textContent||'') && x.children.length===0); return n && n.textContent.replace(/\\s+/g,' ').trim(); }"))
        rec("export.descriptor", page.evaluate("() => { const d = exportDescriptor(); return d && { tab: d.tab, columns: d.columns, served: d.served, total: d.total, scope: d.scope, filter: d.filter, sort: d.sort, rows: d.rows.length }; }"))

        # namespace filter on the flat list
        sel = page.locator("#ns-pick")
        if sel.count():
            opts = page.evaluate("() => [...document.querySelector('#ns-pick').options].map(o => o.value)")
            pick = next((o for o in opts if o not in ("all",)), None)
            if pick:
                page.select_option("#ns-pick", pick); page.wait_for_timeout(1400)
                rec("grants.filtered", page.evaluate("""(ns) => ({ picked: ns, view_ns: view.nsNamespace,
                    request_namespace: data.userBindings.namespace, total: data.userBindings.total, served: (data.userBindings.bindings||[]).length,
                    kpis: [...document.querySelectorAll('#main .kpis .kpi')].map(k => [(k.querySelector('.label')||{}).textContent.trim(), (k.querySelector('.value')||{}).textContent.trim()]),
                    clear: (document.querySelector('[data-ns-pick-clear]')||{textContent:null}).textContent,
                    rows: [...document.querySelectorAll('#every-grant table.audit-table tbody tr')].map(tr => [...tr.children].map(td => td.textContent.replace(/\\s+/g,' ').trim())),
                    empty: (document.querySelector('#every-grant .empty-note')||{textContent:null}).textContent })""", pick))
                page.click("[data-ns-pick-clear]"); page.wait_for_timeout(1400)
                rec("grants.cleared", page.evaluate("() => ({ view_ns: view.nsNamespace, served: (data.userBindings.bindings||[]).length })"))

        # ── the Namespaces card ──────────────────────────────────────────────────────────
        rec("namespaces.card", page.evaluate("""() => { const secs = [...document.querySelectorAll('#main > section.card')];
            const s = secs.find(x => /^Namespaces/.test((x.querySelector('h2')||{textContent:''}).textContent));
            if (!s) return null;
            return { heading: s.querySelector('h2').textContent.replace(/\\s+/g,' ').trim(),
                notes: [...s.querySelectorAll('.filterbar-note')].map(n => n.textContent.replace(/\\s+/g,' ').trim()),
                columns: [...s.querySelectorAll('thead th')].map(th => ({ text: th.textContent.trim(), cls: th.className })),
                rows: [...s.querySelectorAll('tbody tr')].slice(0,6).map(tr => [...tr.children].map(td => td.textContent.replace(/\\s+/g,' ').trim())),
                row_count: s.querySelectorAll('tbody tr').length,
                drillable: !!s.querySelector('tbody .drill'), rowlink: !!s.querySelector('tr.rowlink') }; }"""))
        page.fill("#f-ns-search", "zzzz-no-match"); page.wait_for_timeout(500)
        rec("namespaces.empty_filtered", page.evaluate("""() => { const secs = [...document.querySelectorAll('#main > section.card')];
            const s = secs.find(x => /^Namespaces/.test((x.querySelector('h2')||{textContent:''}).textContent));
            return s && { heading: s.querySelector('h2').textContent.replace(/\\s+/g,' ').trim(),
                empty: (s.querySelector('.empty-note')||{textContent:''}).textContent.replace(/\\s+/g,' ').trim(),
                also: [...s.querySelectorAll('.filterbar-note')].map(n => n.textContent.replace(/\\s+/g,' ').trim()).slice(-1)[0] }; }"""))
        page.fill("#f-ns-search", "demo"); page.wait_for_timeout(500)
        rec("namespaces.filtered", page.evaluate("""() => { const secs = [...document.querySelectorAll('#main > section.card')];
            const s = secs.find(x => /^Namespaces/.test((x.querySelector('h2')||{textContent:''}).textContent));
            return s && { heading: s.querySelector('h2').textContent.replace(/\\s+/g,' ').trim(),
                also: [...s.querySelectorAll('.filterbar-note')].map(n => n.textContent.replace(/\\s+/g,' ').trim()).find(t => /also matching|search everything/.test(t)),
                rows: s.querySelectorAll('tbody tr').length }; }"""))
        shot(page, "live-03-namespaces-card-1280.png", sel="#main > section.card:last-of-type")
        page.fill("#f-ns-search", ""); page.wait_for_timeout(400)

        # ── the drill-down ───────────────────────────────────────────────────────────────
        target = page.evaluate("""() => { const rows = data.userBindings.by_namespace || [];
            const r = rows.find(x => x.namespace !== '(cluster-scoped)'); return r && r.namespace; }""")
        page.goto(BASE + f"/#page=nsaudit&ns={target}", wait_until="networkidle")
        page.wait_for_function("() => data.ns && data.ns.name", timeout=30_000); page.wait_for_timeout(900)
        rec("detail.target", target)
        rec("detail.api", page.evaluate("""() => { const d = data.ns; return { name: d.name, present: d.present, scope: d.scope,
            labels: d.labels, label_keys: d.label_keys, sibling_key: d.sibling_key, siblings: d.siblings, people: d.people,
            via_groups: d.via_groups, cluster_wide_groups: d.cluster_wide_groups, cluster_wide_grants: d.cluster_wide_grants,
            direct_grants: d.direct_grants, changes: d.changes, retention: d.retention }; }"""))
        rec("detail.cards", page.evaluate("() => [...document.querySelectorAll('#main > section.card h2')].map(h => h.textContent.replace(/\\s+/g,' ').trim())"))
        rec("detail.kpis", page.evaluate("""() => [...document.querySelectorAll('#main .kpis .kpi')].map(k => ({
            label: (k.querySelector('.label')||{}).textContent.trim(), value: (k.querySelector('.value')||{}).textContent.trim(),
            value_cls: (k.querySelector('.value')||{}).className }))"""))
        rec("detail.notes", page.evaluate("() => [...document.querySelectorAll('#main .filterbar-note, #main .empty-note, #main .muted.text-xs')].map(n => n.textContent.replace(/\\s+/g,' ').trim())"))
        rec("detail.tables", page.evaluate("""() => [...document.querySelectorAll('#main table')].map(t => ({
            columns: [...t.querySelectorAll('thead th')].map(th => th.textContent.trim()),
            rows: [...t.querySelectorAll('tbody tr')].slice(0,8).map(tr => [...tr.children].map(td => td.textContent.replace(/\\s+/g,' ').trim())),
            count: t.querySelectorAll('tbody tr').length }))"""))
        rec("detail.badges", page.evaluate("() => [...document.querySelectorAll('#main .badge')].map(b => ({ cls: b.className, text: b.textContent.replace(/\\s+/g,' ').trim() }))"))
        rec("detail.back", page.evaluate("() => (document.querySelector('#back')||{textContent:null}).textContent"))
        rec("detail.export", page.evaluate("() => exportDescriptor()"))
        shot(page, "live-04-ns-detail-1280.png", full=True)

        # ── 375 px on the live page ──────────────────────────────────────────────────────
        page.set_viewport_size({"width": 375, "height": 800}); page.wait_for_timeout(600)
        rec("live.375.detail", page.evaluate("() => ({ scrollWidth: document.documentElement.scrollWidth, innerWidth, ok: document.documentElement.scrollWidth <= innerWidth })"))
        shot(page, "live-05-ns-detail-375.png", full=True)
        open_audit(page); page.wait_for_timeout(600)
        rec("live.375.audit", page.evaluate("() => ({ scrollWidth: document.documentElement.scrollWidth, innerWidth, ok: document.documentElement.scrollWidth <= innerWidth })"))
        shot(page, "live-06-audit-375.png", full=True)

        rec("errors", errors)
        (OUT / "capture.json").write_text(json.dumps(REC, indent=1, ensure_ascii=False) + "\n")
        print("wrote                   :", OUT / "capture.json", flush=True)
        br.close()
        sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
