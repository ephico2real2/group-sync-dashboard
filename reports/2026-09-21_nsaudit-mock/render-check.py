#!/usr/bin/env python3
"""Render check for docs/design/nsaudit-mock.html — the step `node --check` cannot do.

Renders the mock headlessly, DRIVES every interactive control and asserts the resulting state
(not merely that nothing threw), re-renders at 375 / 393 / 768 / 1280 asserting no horizontal
overflow and nothing clipped inside an overflow:hidden box, and measures CONTRAST from the
painted pixels — the body wash is `background-attachment: fixed`, so the accent bloom is placed
against the viewport and cannot be computed from the token values.

Every printed line is a measurement. Exit 1 on any failure; the failures are listed at the end.
Writes NN-*.png beside itself."""
import io, json, pathlib, sys
from PIL import Image
from playwright.sync_api import sync_playwright

OUT = pathlib.Path(__file__).resolve().parent
MOCK = OUT.parents[1] / "docs" / "design" / "nsaudit-mock.html"
URL = MOCK.as_uri()
FAIL, NOTES = [], {}

def check(name, got, want=None, ok=None):
    good = (got == want) if ok is None else ok
    print(("PASS " if good else "FAIL ") + f"{name:52s} {json.dumps(got, ensure_ascii=False)[:200]}"
          + ("" if good or want is None else f"  (wanted {json.dumps(want, ensure_ascii=False)[:120]})"))
    if not good: FAIL.append(name)
    return good

def note(name, value):
    NOTES[name] = value
    print(f"     {name:52s} {json.dumps(value, ensure_ascii=False)[:240]}")

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


def shot(page, name, full=False):
    page.wait_for_timeout(250)
    page.screenshot(path=str(OUT / name), full_page=full)
    print("     shot                                                 " + name + "  " + crop(OUT / name))

def lin(c):
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
def lum(rgb): return 0.2126 * lin(rgb[0]) + 0.7152 * lin(rgb[1]) + 0.0722 * lin(rgb[2])
def ratio(a, b):
    la, lb = lum(a), lum(b); hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)
def parse(css):
    return tuple(int(x) for x in css[css.index("(") + 1:css.index(")")].replace("/", ",").split(",")[:3])

TXT = "() => document.body.textContent.replace(/\\s+/g, ' ')"
CARDS = "() => [...document.querySelectorAll('#main > section.card')].map(s => (s.querySelector('h2,h3')||{textContent:''}).textContent.replace(/\\s+/g,' ').trim())"
WORKLIST_NS = "() => [...document.querySelectorAll('#main table')].slice(1,2).flatMap(t => [...t.querySelectorAll('tbody tr')].map(r => r.querySelector('[data-ns]') ? r.querySelector('[data-ns]').textContent.trim() : r.children[1].textContent.trim()))"

def drive(page):
    # ── it rendered at all ────────────────────────────────────────────────────────────────────
    cards = page.evaluate(CARDS)
    check("the page renders its cards", cards, ok=len(cards) == 8)
    note("cards", cards)
    check("the shell carries Refresh and Sign out",
          page.evaluate("() => [!!document.querySelector('#refresh'), !!document.querySelector('#logout')]"), [True, True])
    check("the tab strip is the app's 14",
          page.evaluate("() => document.querySelectorAll('.tab').length"), 14)
    check("Namespace audit is the current tab",
          page.evaluate("() => (document.querySelector('.tab[aria-current=page]')||{}).textContent"), "Namespace audit")
    note("scope pill", page.evaluate("() => document.querySelector('#scope-pill').textContent"))
    note("build info", page.evaluate("() => document.querySelector('#build-info').textContent"))
    check("the verdict names the worst tier",
          page.evaluate("() => document.querySelector('.verdict .badge').textContent.trim()"), "High exposure")
    check("the unit chart draws one cell per rollup entry",
          page.evaluate("() => document.querySelectorAll('.unit .cell').length"), 5)
    check("the cluster scope's cell is ringed, not passed off as a namespace",
          page.evaluate("() => [...document.querySelectorAll('.unit .cell')].filter(c => c.classList.contains('scope')).map(c => c.title)"),
          ["the cluster scope — high"])
    check("every risk shape is painted, never an empty span",
          page.evaluate("() => [...document.querySelectorAll('.unit .cell .shape')].map(s => { const r = s.getBoundingClientRect(); return Math.round(r.width) + 'x' + Math.round(r.height); })"),
          ["18x18"] * 5)
    check("the cluster-scope cell's ring is actually painted (a clip-path would have eaten it)",
          page.evaluate("() => { const c = document.querySelector('.unit .cell.scope'); const cs = getComputedStyle(c); return [cs.outlineStyle, cs.outlineWidth]; }"),
          ["dashed", "2px"])
    check("the KPI row is the five the page shipped",
          page.evaluate("() => [...document.querySelectorAll('#main .kpis .kpi .label')].map(l => l.textContent.trim())"),
          ["Namespaces at risk", "People exposed", "Grants to migrate", "Critical", "High"])
    check("the KPI values are the measured ones",
          page.evaluate("() => [...document.querySelectorAll('#main .kpis .kpi .value')].map(v => v.textContent.trim())"),
          ["5", "8", "11", "0", "2"])
    check("no row of the worklist is the pseudo-namespace",
          page.evaluate(WORKLIST_NS), ok="(cluster-scoped)" not in page.evaluate(WORKLIST_NS))
    check("the cluster-wide card lists the three people",
          page.evaluate("""() => [...document.querySelectorAll('#main > section.card')][1].querySelectorAll('tbody tr').length"""), 3)
    check("every badge carries a glyph AND a word",
          page.evaluate("""() => [...document.querySelectorAll('.badge')].every(b =>
              b.querySelector('.glyph') && b.textContent.trim().length > 0)"""), True)
    check("no badge states anything in colour alone (each shape is distinct)",
          page.evaluate("""() => { const seen = {};
              ['risk-critical','risk-high','risk-medium','risk-low'].forEach(k => {
                const el = document.createElement('span'); el.className = 'badge ' + k;
                el.innerHTML = '<span class="glyph"></span>'; document.body.appendChild(el);
                seen[k] = getComputedStyle(el.querySelector('.glyph')).clipPath + '|' + getComputedStyle(el.querySelector('.glyph')).borderRadius + '|' + getComputedStyle(el.querySelector('.glyph')).borderTopWidth;
                el.remove(); });
              return new Set(Object.values(seen)).size; }"""), 4)
    check("the risk reasoning is on the page",
          page.evaluate(TXT + ".includes('one forgotten cluster-admin matters more than twenty view grants')"), True)
    check("the WHO_PREVIEW reasoning is on the page",
          page.evaluate(TXT + ".includes('the names are corroboration')"), True)
    check("the runbook keeps its five steps",
          page.evaluate("() => document.querySelectorAll('.runbook li').length"), 5)
    check("the runbook's command is filled from the worst row",
          page.evaluate("() => document.querySelector('.runbook .cmd').textContent.trim()"),
          "oc delete rolebinding asmith-admin -n legacy-payments")
    check("the operational goal survives",
          page.evaluate(TXT + ".includes('Operational goal: zero rows on this page')"), True)

    # ── sorting ───────────────────────────────────────────────────────────────────────────────
    before = page.evaluate(WORKLIST_NS)
    note("worklist, risk order", before)
    page.click("#main table >> nth=1 >> css=th:nth-child(2) button.sorter")
    page.wait_for_timeout(150)
    after = page.evaluate(WORKLIST_NS)
    check("sorting by Namespace re-orders the worklist", after != before, ok=after != before)
    note("worklist, namespace desc", after)
    check("aria-sort follows the click",
          page.evaluate("() => [...document.querySelectorAll('#main table')][1].querySelectorAll('th')[1].getAttribute('aria-sort')"), "descending")
    check("Restore risk order appears once the order is not the default",
          page.evaluate("() => !!document.querySelector('#ns-reset')"), True)
    page.click("#ns-reset"); page.wait_for_timeout(150)
    check("Restore risk order puts it back", page.evaluate(WORKLIST_NS), before)
    check("and then removes itself", page.evaluate("() => !!document.querySelector('#ns-reset')"), False)

    # ── the one filter box, now reaching both lists ───────────────────────────────────────────
    page.fill("#f-ns-search", "legacy"); page.wait_for_timeout(250)
    check("the box filters the worklist too", page.evaluate(WORKLIST_NS), ["legacy-payments", "legacy-reporting"])
    check("and the namespace list with it",
          page.evaluate("() => document.querySelectorAll('#main > section.card:nth-of-type(7) tbody tr').length"), 2)
    note("headings while filtered", page.evaluate("() => [...document.querySelectorAll('#main h2')].map(h => h.textContent.replace(/\\s+/g,' ').trim())"))
    check("the caret stays at the end of what was typed",
          page.evaluate("() => [document.activeElement.id, document.activeElement.selectionStart]"), ["f-ns-search", 6])
    page.fill("#f-ns-search", "zzzz"); page.wait_for_timeout(250)
    check("an empty result says the filter is hiding them, with the denominator",
          page.evaluate("() => [...document.querySelectorAll('.empty-note')].map(e => e.textContent.replace(/\\s+/g,' ').trim())"),
          ok=any("still there" in t for t in page.evaluate("() => [...document.querySelectorAll('.empty-note')].map(e => e.textContent)")))
    page.focus("#f-ns-search"); page.keyboard.press("Escape"); page.wait_for_timeout(250)
    check("Escape clears the box", page.evaluate("() => document.querySelector('#f-ns-search').value"), "")
    check("and the worklist comes back", page.evaluate(WORKLIST_NS), before)

    # ── the flat list, its selector and its disclosure ────────────────────────────────────────
    check("Every grant is collapsed by default",
          page.evaluate("() => document.querySelector('#every-grant').hasAttribute('hidden')"), True)
    check("the disclosure states the count",
          page.evaluate("() => document.querySelector('[data-toggle=grantsOpen]').textContent.replace(/\\s+/g,' ').trim()"), "▸ Show 11 grants")
    check("collapsed by default is the shipped behaviour, kept",
          page.evaluate("() => document.querySelector('[data-toggle=grantsOpen]').getAttribute('aria-expanded')"), "false")
    page.click("[data-toggle=grantsOpen]"); page.wait_for_timeout(200)
    check("it opens", page.evaluate("() => document.querySelector('#every-grant').hasAttribute('hidden')"), False)
    check("aria-expanded follows it",
          page.evaluate("() => document.querySelector('[data-toggle=grantsOpen]').getAttribute('aria-expanded')"), "true")
    check("all eleven grants render",
          page.evaluate("() => document.querySelectorAll('#every-grant tbody tr').length"), 11)
    page.select_option("#ns-pick", "legacy-payments"); page.wait_for_timeout(250)
    check("the namespace selector filters the flat list",
          page.evaluate("() => [...document.querySelectorAll('#every-grant tbody tr')].map(r => r.children[0].textContent.trim())"),
          ["asmith", "bwilliams", "jdoe"])
    check("the five headline numbers do not move when it is filtered",
          page.evaluate("() => [...document.querySelectorAll('#main .kpis .kpi .value')].map(v => v.textContent.trim())"),
          ["5", "8", "11", "0", "2"])
    check("Clear filter appears", page.evaluate("() => !!document.querySelector('#ns-pick-clear')"), True)
    page.click("#ns-pick-clear"); page.wait_for_timeout(250)
    check("and restores the eleven", page.evaluate("() => document.querySelectorAll('#every-grant tbody tr').length"), 11)
    page.click("#main table >> nth=2 >> css=th:nth-child(1) button.sorter"); page.wait_for_timeout(200)
    note("flat list sorted by person", page.evaluate("() => [...document.querySelectorAll('#every-grant tbody tr')].map(r => r.children[0].textContent.trim())"))
    check("the flat list sorts by person",
          page.evaluate("() => document.querySelectorAll('#every-grant tbody tr')[0].children[0].textContent.trim()"), "tmp-contractor-9931")

    # ── the bounded roster, in the shape box where the lab has no row for it ──────────────────
    check("the roster preview shows the bound's worth",
          page.evaluate("() => document.querySelectorAll('.shape-ex .who .chip').length"), 4)
    check("with an honest count of the rest",
          page.evaluate("() => document.querySelector('#shape-who').textContent.trim()"), "+5 more")
    page.click("#shape-who"); page.wait_for_timeout(200)
    check("expanding shows all nine",
          page.evaluate("() => document.querySelectorAll('.shape-ex .who .chip').length"), 9)
    check("and offers to fold again",
          page.evaluate("() => document.querySelector('#shape-who').textContent.trim()"), "show fewer")
    page.click("#shape-who"); page.wait_for_timeout(200)

    # ── the counts disclosure ─────────────────────────────────────────────────────────────────
    page.click("[data-toggle=countsOpen]"); page.wait_for_timeout(200)
    check("the how-counted note opens",
          page.evaluate("() => !document.querySelector('#counts-note').hasAttribute('hidden')"), True)
    check("and names the double-counting trap",
          page.evaluate("() => document.querySelector('#counts-note').textContent.replace(/\\s+/g,' ').includes('the sum says 11 where the truth is 8')"), True)
    check("and explains why the tile reads 5 where the table holds 4",
          page.evaluate("() => document.querySelector('#counts-note').textContent.replace(/\\s+/g,' ').includes('5 and not 4: the rollup carries the cluster scope as one more entry')"), True)

    # ── the drill ─────────────────────────────────────────────────────────────────────────────
    page.click("[data-ns='legacy-payments'] >> nth=0"); page.wait_for_timeout(300)
    check("a namespace in the worklist opens the namespace",
          page.evaluate("() => document.querySelector('#main h2').textContent.trim()"), "legacy-payments")
    check("the detail KPI row adds the cluster-wide reach",
          page.evaluate("() => [...document.querySelectorAll('#main .kpis .kpi .label')].map(l => l.textContent.trim())"),
          ["mnemonic", "app-environment", "oud-group", "People who reach it", "Via groups", "Direct grants", "Reached cluster-wide"])
    check("and its value is the 53 the sentence used to bury",
          page.evaluate("() => [...document.querySelectorAll('#main .kpis .kpi .value')].map(v => v.textContent.trim()).slice(-1)[0]"), "53")
    check("the cluster-wide list is closed until asked for",
          page.evaluate("() => document.querySelector('#wide-list').hasAttribute('hidden')"), True)
    page.click("[data-toggle=wideOpen]"); page.wait_for_timeout(250)
    check("it opens as a table of the 16 that name someone",
          page.evaluate("() => document.querySelectorAll('#wide-list tbody tr').length"), 16)
    page.click("[data-toggle=platformOpen]"); page.wait_for_timeout(250)
    check("the platform groups fold out, most-bound first",
          page.evaluate("() => [...document.querySelectorAll('#platform-list .chip')].map(c => c.textContent.trim()).slice(0,3)"),
          ["system:authenticated × 18", "system:nodes × 4", "system:authenticated:oauth × 2"])
    check("direct grants are named and badged",
          page.evaluate("""() => [...document.querySelectorAll('#main > section.card')].some(c =>
              /^Direct grants/.test((c.querySelector('h3')||{textContent:''}).textContent))"""), True)
    check("history keeps its first-observed reading",
          page.evaluate(TXT + ".includes('A first observation is not a grant')"), True)
    note("detail cards", page.evaluate(CARDS))
    shot(page, "mock-02-namespace-detail-1280.png", full=True)
    page.click("#back"); page.wait_for_timeout(300)
    check("back returns to the audit", page.evaluate("() => document.querySelector('#main h2').textContent.trim()"), "Namespace audit")
    page.click("#main > section.card:nth-of-type(7) [data-ns] >> nth=0"); page.wait_for_timeout(300)
    check("a namespace with no captured payload says so rather than inventing one",
          page.evaluate(TXT + ".includes('Rather than draw a plausible')"), True)
    page.click("#back"); page.wait_for_timeout(250)

    # ── the tiers ─────────────────────────────────────────────────────────────────────────────
    page.select_option("#f-tier", "self-jdoe"); page.wait_for_timeout(300)
    check("the self view renders the viewer's own three grants",
          page.evaluate("() => document.querySelectorAll('#main table tbody tr').length"), 3)
    check("and no cluster aggregate at all",
          page.evaluate("() => document.querySelectorAll('#main .kpis').length"), 0)
    check("the scope pill narrows with it",
          page.evaluate("() => document.querySelector('#scope-pill').textContent"), "Narrowed view — you are seeing your own access")
    shot(page, "mock-03-self-tier-1280.png", full=True)
    page.select_option("#f-tier", "self-alice"); page.wait_for_timeout(300)
    check("a viewer with none gets the sentence, not an empty table",
          page.evaluate("() => document.querySelector('#main .empty-note').textContent.replace(/\\s+/g,' ').includes('This says nothing about whether OTHER accounts hold direct grants')"), True)
    page.select_option("#f-tier", "withheld"); page.wait_for_timeout(300)
    check("the refusal is withheld-not-empty",
          page.evaluate("() => document.querySelector('.scope-refusal').textContent.replace(/\\s+/g,' ').trim()"),
          ok=page.evaluate("() => document.querySelector('.scope-refusal').textContent").strip().startswith("Withheld, not empty."))
    check("and the export offers nothing to export",
          page.evaluate("() => !document.querySelector('#export-csv')"), True)
    shot(page, "mock-04-withheld-1280.png", full=True)
    page.select_option("#f-tier", "admin"); page.wait_for_timeout(300)

    # ── the cluster selector ──────────────────────────────────────────────────────────────────
    page.select_option("#f-cluster", "mock-trusted"); page.wait_for_timeout(300)
    check("a second measured cluster renders its own numbers",
          page.evaluate("() => [...document.querySelectorAll('#main .kpis .kpi .value')].map(v => v.textContent.trim())"),
          ["1", "1", "1", "0", "0"])
    check("with no cluster-wide finding it says so",
          page.evaluate(TXT + ".includes('No binding names a person at the cluster scope')"), True)
    page.select_option("#f-cluster", "mock-privateca"); page.wait_for_timeout(300)
    check("a cluster with no captured payload refuses to pretend",
          page.evaluate("() => document.querySelector('#f-cluster').value"), "mock-trusted")
    page.select_option("#f-cluster", "dashboard-rnd"); page.wait_for_timeout(300)

    # ── appearance and colour ─────────────────────────────────────────────────────────────────
    page.select_option("#pref-mode", "dark"); page.wait_for_timeout(300)
    check("Appearance sets data-theme", page.evaluate("() => document.documentElement.getAttribute('data-theme')"), "dark")
    note("dark page background", page.evaluate("() => getComputedStyle(document.body).backgroundColor"))
    shot(page, "mock-05-dark-1280.png", full=True)
    page.select_option("#pref-palette", "deuter"); page.wait_for_timeout(300)
    check("Colours sets data-palette", page.evaluate("() => document.documentElement.getAttribute('data-palette')"), "deuter")
    note("deuter critical/warning", page.evaluate("""() => { const cs = getComputedStyle(document.documentElement);
        return [cs.getPropertyValue('--status-critical').trim(), cs.getPropertyValue('--status-warning').trim()]; }"""))
    page.select_option("#pref-palette", ""); page.select_option("#pref-mode", ""); page.wait_for_timeout(300)
    check("both controls clear back to auto",
          page.evaluate("() => [document.documentElement.hasAttribute('data-theme'), document.documentElement.hasAttribute('data-palette')]"), [False, False])
    page.click("#refresh"); page.wait_for_timeout(250)
    check("Refresh repaints without losing the page",
          page.evaluate("() => document.querySelectorAll('#main > section.card').length"), 8)


def widths(page):
    for w, h in ((375, 812), (393, 852), (768, 1024), (1280, 1000)):
        page.set_viewport_size({"width": w, "height": h}); page.wait_for_timeout(450)
        geo = page.evaluate("""() => ({ scrollWidth: document.documentElement.scrollWidth, innerWidth,
            widest: Math.max(...[...document.querySelectorAll('#main *')].map(e => e.getBoundingClientRect().right)) })""")
        check(f"{w}px — no horizontal overflow", geo["scrollWidth"] <= geo["innerWidth"], ok=geo["scrollWidth"] <= geo["innerWidth"])
        check(f"{w}px — nothing laid out past the viewport", round(geo["widest"]), ok=geo["widest"] <= geo["innerWidth"] + 1)
        note(f"{w}px geometry", {k: round(v) for k, v in geo.items()})
        clipped = page.evaluate("""() => [...document.querySelectorAll('*')].filter(e => {
            const cs = getComputedStyle(e);
            if (cs.overflowX !== 'hidden' && cs.overflowY !== 'hidden') return false;
            if (e === document.documentElement || e === document.body) return false;
            if (e.classList.contains('sr-only')) return false;   // clip: rect(0 0 0 0) IS the point
            return e.scrollWidth > e.clientWidth + 1 || e.scrollHeight > e.clientHeight + 1;
          }).map(e => e.tagName + '.' + e.className + ' ' + e.scrollWidth + '>' + e.clientWidth
                      + ' ' + e.scrollHeight + '>' + e.clientHeight)""")
        check(f"{w}px — nothing clipped inside an overflow:hidden box", clipped, [])
        page.evaluate("() => window.scrollTo(0, 0)")
        shot(page, f"mock-0{6 if w == 375 else 7 if w == 393 else 8 if w == 768 else 9}-audit-{w}.png", full=True)
    page.set_viewport_size({"width": 375, "height": 812}); page.wait_for_timeout(300)
    check("375px — the worklist stacks rather than scrolling sideways",
          page.evaluate("""() => { const t = [...document.querySelectorAll('#main table')][1];
              return getComputedStyle(t.querySelector('tbody tr')).display; }"""), "block")
    check("375px — each stacked cell keeps its column name",
          page.evaluate("""() => { const t = [...document.querySelectorAll('#main table')][1];
              return [...t.querySelectorAll('tbody tr:first-child td')].map(td => td.dataset.l); }"""),
          ["Risk", "Namespace", "Highest privilege", "People", "Grants", "Who is exposed"])
    page.set_viewport_size({"width": 1280, "height": 1000}); page.wait_for_timeout(300)


TOP_BAND = [("h1", "header.top h1"), ("cluster sub", "header.top .sub"), ("scope pill", "#scope-pill"),
            ("build info", "#build-info"), ("Appearance label", "label[for='pref-mode']"),
            ("active tab", ".tab[aria-current='page']"), ("inactive tab", ".tab:not([aria-current])"),
            ("filter label", ".filters label"), ("filter muted", ".filters .muted")]

def contrast(page, theme):
    """The painted ground under every piece of text in the wash's band, and its contrast.
    Children of <body> are hidden so the wash paints alone; visibility is inherited, so the
    cards go with them and what is left is exactly the ground a reader's eye receives."""
    page.evaluate("(t) => { if (t) document.documentElement.setAttribute('data-theme', t); else document.documentElement.removeAttribute('data-theme'); }", theme)
    page.wait_for_timeout(300)
    boxes = page.evaluate("""(sel) => sel.map(([label, s]) => { const el = document.querySelector(s); if (!el) return [label, null];
        const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
        return [label, { x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
                         color: cs.color, size: cs.fontSize, weight: cs.fontWeight }]; })""", TOP_BAND)
    page.evaluate("() => { [...document.body.children].forEach(el => { el.dataset.wasVis = el.style.visibility; el.style.visibility = 'hidden'; }); }")
    page.wait_for_timeout(250)
    img = Image.open(io.BytesIO(page.screenshot())).convert("RGB")
    page.evaluate("() => { [...document.body.children].forEach(el => { el.style.visibility = el.dataset.wasVis || ''; }); }")
    rows, worst = [], (99, "")
    for label, b in boxes:
        if not b: continue
        g = img.getpixel((min(b["x"], img.width - 1), min(b["y"], img.height - 1)))
        r = ratio(parse(b["color"]), g)
        large = float(b["size"][:-2]) >= 24 or (float(b["size"][:-2]) >= 18.66 and int(b["weight"]) >= 700)
        bar = 3.0 if large else 4.5
        rows.append({"element": label, "y": b["y"], "colour": b["color"], "size": b["size"] + "/" + b["weight"],
                     "ground": "#%02x%02x%02x" % g, "ratio": round(r, 2), "bar": bar})
        if r - bar < worst[0]: worst = (r - bar, label)
        check(f"{theme or 'light'} — {label} on the painted wash ≥ {bar}", round(r, 2), ok=r >= bar)
    ground = ["#%02x%02x%02x" % img.getpixel((640, y)) for y in (0, 40, 120, 200, 300, 420, 700)]
    note(f"{theme or 'light'} ground at x=640, y=0…700", ground)
    note(f"{theme or 'light'} tightest element", worst[1])
    NOTES[f"contrast-{theme or 'light'}"] = rows
    return rows


# ── The contract check ────────────────────────────────────────────────────────────────────────
# The one risk this whole exercise exists to avoid: `docs/design/tab-feature-contract.md` was
# written because an earlier pass "reduced these pages to headline + KPIs + a table, and in doing
# so deleted most of their value". Each entry is the distinctive clause of one caveat the live
# page carries (measured into docs/design/nsaudit-feature-capture.md). A caveat behind a
# disclosure still counts — the states below are driven — but one that renders in no state at all
# is a caveat that was deleted, which is what this asserts.
CAVEATS = {
    "riskTier ranks on privilege, not count": "not by count",
    "riskTier: one forgotten cluster-admin": "one forgotten cluster-admin matters more than twenty",
    "WHO_PREVIEW: the names are corroboration": "the names are corroboration",
    "WHO_PREVIEW: why the roster is bounded": "would decide the width of the whole table",
    "the KPIs come from the rollup": "never pages and never filters",
    "the double-count the union avoids": "the sum says 11 where the truth is 8",
    "the platform exclusion, stated": "break-glass and cluster-internal, with nowhere to migrate to",
    "why 1 — offboarding does not revoke it": "keeps granting after they leave the team",
    "why 2 — invisible to access review": "a clean review can coexist with standing access nobody approved",
    "why 3 — no approval trail": "records only who ran",
    "runbook: work top-down": "the table above is already in the order to do it in",
    "runbook: wait one sync": "deleting first leaves them locked out",
    "runbook: the operational goal": "operational goal:",
    "runbook: clean is clean": "an access review that reads clean",
    "the flat list is collapsed on purpose": "costs time nobody gets value from",
    "the flat list is not the view to work from": "the per-namespace table above is the view to work from",
    "truncation: ranked below, not hidden": "they are ranked below these",
    "the namespace filter is server-side": "server-side",
    "namespaces: not only those with a grant": "not only those with a grant",
    "namespaces: the third drill-down": "the third drill-down beside groups and users",
    "namespaces: zero in both": "a namespace with zero in both is a result an access review wants to confirm",
    "namespaces: the filter is hiding them": "the filter is hiding them",
    "namespaces: a refused read cannot attest absence": "cannot attest absence",
    "self: no wide aggregate is recomputed": "none of the wide view's aggregates",
    "self: says nothing about other accounts": "says nothing about whether other accounts hold direct grants",
    "self: a direct grant survives offboarding": "a direct grant survives offboarding",
    "self: your view, not the cluster": "that is your view, not the cluster",
    "refusal: withheld, not empty": "withheld, not empty",
    "refusal: for administrators only": "for administrators only",
    "namespace refusal: deliberately indistinguishable": "deliberately indistinguishable",
    "detail: outside the naming convention": "outside the naming convention",
    "detail: the answer the triangle exists for": "the answer the triangle exists for",
    "detail: the goal for this card is zero": "the operational goal for this card is zero",
    "detail: virtual groups hold no person": "authorise access but hold no person",
    "detail: zero in both could never happen": "could never happen",
    "detail: retention cut it, nothing else": "does not mean nothing happened before",
    "detail: no change recorded since watching began": "no binding change recorded here",
    "the zero state: offboarding is one action": "that is what makes offboarding a single action",
    "loading is a real state": "loading",
    "export says what it downloads": "never more than the server served you",
}


def caveats(page):
    """Collect the page's text across every state it has, then assert every caveat survives."""
    import re
    texts = []
    grab = lambda: texts.append(page.evaluate("() => document.body.innerText"))
    # Set the disclosure state, never toggle it: drive() has already opened these, and a click
    # here would close them — which is how this sweep first reported two caveats missing that
    # were on the page the whole time.
    page.evaluate("""() => { MOCK.view.ns = null; MOCK.view.tier = 'admin';
        MOCK.view.countsOpen = true; MOCK.view.grantsOpen = true; MOCK.render(); }""")
    page.wait_for_timeout(250)
    grab()
    page.select_option("#ns-pick", "legacy-payments"); page.wait_for_timeout(250); grab()
    page.click("#ns-pick-clear"); page.wait_for_timeout(200)
    page.fill("#f-ns-search", "zzzz"); page.wait_for_timeout(250); grab()
    page.fill("#f-ns-search", ""); page.wait_for_timeout(200)
    for tier in ("self-jdoe", "self-alice", "withheld"):
        page.select_option("#f-tier", tier); page.wait_for_timeout(250); grab()
    page.select_option("#f-tier", "admin"); page.wait_for_timeout(250)
    for ns in ("legacy-payments", "demo-prod"):
        page.evaluate("(n) => { MOCK.view.ns = n; MOCK.view.wideOpen = true; MOCK.view.platformOpen = true; MOCK.render(); }", ns)
        page.wait_for_timeout(250); grab()
    page.evaluate("() => { MOCK.view.ns = null; MOCK.render(); }"); page.wait_for_timeout(200)
    # Titles too: the export buttons carry their honesty sentence as a tooltip, which innerText omits.
    texts.append(page.evaluate("() => [...document.querySelectorAll('[title]')].map(e => e.title).join(' || ')"))
    blob = re.sub(r"\s+", " ", " ".join(texts)).strip().lower()
    missing = [k for k, v in CAVEATS.items() if re.sub(r"\s+", " ", v).strip().lower() not in blob]
    for k in CAVEATS:
        if k in missing:
            check(f"caveat kept — {k}", CAVEATS[k], ok=False)
    check(f"every one of the {len(CAVEATS)} caveats the live page carries is reachable here",
          len(CAVEATS) - len(missing), len(CAVEATS))
    note("states swept for caveats", len(texts))


def main():
    print(f"mock: {MOCK}\n")
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(viewport={"width": 1280, "height": 1000})
        page = ctx.new_page()
        errors, console = [], []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: console.append(m.type + ": " + m.text) if m.type in ("error", "warning") else None)
        page.goto(URL, wait_until="load"); page.wait_for_timeout(600)
        drive(page)
        caveats(page)
        widths(page)
        contrast(page, None)
        contrast(page, "dark")
        page.evaluate("() => document.documentElement.removeAttribute('data-theme')")
        check("no uncaught error", errors, [])
        check("no console error or warning", console, [])
        (OUT / "render-check.json").write_text(json.dumps(NOTES, indent=1) + "\n")
        br.close()
    print("\n" + ("ALL CHECKS PASSED" if not FAIL else f"{len(FAIL)} FAILED:\n  " + "\n  ".join(FAIL)))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
