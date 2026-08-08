# Review — feat/group-search

**Status: OPEN. One pass, Fable, extra-high effort. Scope is this branch alone.**

Two commits on top of `main`, rebased after PR #12 merged.

| commit | what |
|---|---|
| `feat(ui): free-text search on the Groups tab, ANDing every word` | a filter box; `matchesGroupSearch`; focus/caret preservation in `renderFilters`; honest denominator in the header; 11 browser tests |
| `refactor(ui): lift the stylesheet out of index.html into /static/app.css` | 725 lines of CSS moved to a same-origin `<link>`; two tests re-pointed at the file; a guard that no inline `<style>` returns |

Files: `local-development/gsd/static/index.html`, `local-development/gsd/static/app.css`,
`local-development/tests/test_ui.py`, `local-development/tests/test_type_scale.py`,
`local-development/tests/test_accessibility.py`, `docs/namespace-report-design.md`.

Suite: `cd local-development && .venv/bin/python -m pytest tests/ -q --deselect tests/test_live_smoke.py`
— baseline on this branch **1049 passed, 1 skipped**; `main` is 1039.

## Claims to test — prefer refutation

- **G1** `matchesGroupSearch` ANDs every whitespace term, is order-independent and case-insensitive, and
  treats the query as literal text — no regex, no globbing. A group name is never interpolated into
  markup by it.
- **G2** The search cannot mislead: while filtering, the header states `N of M` and the empty state says
  the search is hiding rows rather than the data being empty.
- **G3** Focus AND caret survive a filter-bar repaint. `renderFilters` replaces the whole bar's
  `innerHTML` and the page repaints every 30s, so without this the box is unusable. Check the capture
  is by id, that `selectionStart` is read defensively, and that nothing throws inside a render.
- **G4** Filtering issues no network request. The groups endpoint applies no limit, so the whole list is
  already in the browser.
- **G5** A filtered row still drills in, through `navigate()`, landing on a page that can render it.
- **G6** The accessible name of the box is the visible label "Find". The help text is a DESCRIPTION
  behind `aria-describedby` in a `.sr-only` span — `aria-label` must NOT override the name (WCAG 2.5.3
  Label in Name). `.sr-only` must be 1px-clipped, never `display:none`/`visibility:hidden`, or the text
  leaves the accessibility tree.
- **G7** The CSS extraction lost nothing: every custom property and rule `main` had still applies, the
  page has no inline `<style>`, and `/static/app.css` is served (`text/css`, 200).
- **G8** The two stylesheet tests read `app.css`, and the new guard makes a re-inlined block a failure
  rather than an invisible bypass of both.
- **G9** Nothing else regressed: `test_display_timezone.py` slices the page between named landmarks, and
  the extraction moved 725 lines out of that same file.

## Out of scope

- Do not restyle anything, propose a framework, or add a build step. One page, vanilla JS, no build.
- Do not split the JavaScript. That is deliberately deferred: `test_display_timezone.py` slices the page
  between named landmarks, so modules are a test-harness change too, and it wants its own review.
- Do not revisit login capture, the cluster-access gate, or anything merged in PR #12.
- Do not propose server-side search. Measured: the endpoint applies no limit.

## Requirements

Full replacement code in THIS file for every finding, plus a complete test that fails before and passes
after. A file:line, a concrete trigger, and the consequence stated as what a reader would believe that is
false. Comments in this codebase say WHY, not WHAT — a replacement that strips the reasoning is a
regression even when the logic is right. Measure rather than reason: run the suite, drive the page, show
the command and its output. Judge technical debt in the three buckets: DEBT-INTRODUCED / DEBT-ACCEPTED /
DEBT-AVOIDED.

## Fable — findings

Everything below was measured against a live Chromium driven by Playwright and the seeded server from
`tests/test_ui.py`, on this worktree. Every proposed replacement was applied to a scratch copy of
`gsd/static/index.html` outside the repo
(`scratchpad/static_fixed/`), re-driven in the browser, and re-run against the FULL `tests/test_ui.py`:
**122 existing UI tests + the 6 new tests below = 128 passed** on the fixed copy; the 6 new tests all
**fail** on the branch as it stands. The repo itself was not modified.

Suite on this branch, as instructed:

```
cd local-development && .venv/bin/python -m pytest tests/ -q --deselect tests/test_live_smoke.py
1050 passed, 1 skipped, 4 deselected, 1 warning in 124.93s
```

Note the doc's stated baseline (1049 passed) is off by one on this machine — same 1 skipped, 4
deselected. Nothing failed; the arbiter may want to re-pin the number.

### Verdict summary

| Claim | Verdict | One line |
|---|---|---|
| G1 | **CONFIRMED** | AND / order-free / case-free / literal, boolean-only — all measured |
| G2 | **FIX-INADEQUATE** | honest denominator, but the zero-denominator empty state states a falsehood (Finding 2) |
| G3 | **FIX-INADEQUATE** | focus+caret survive and nothing throws — but the same repaint destroys an IME composition (Finding 1) |
| G4 | **CONFIRMED** | endpoint takes only `state`, no limit; zero fetches measured while typing |
| G5 | **CONFIRMED** | filtered row drills in via `navigate()`; measured |
| G6 | **CONFIRMED** | AX tree: role `searchbox`, name `Find`, description = the sr-only sentence |
| G7 | **CONFIRMED** | app.css is the old inline block byte-for-byte plus a header comment; 200 `text/css` |
| G8 | **FIX-INADEQUATE** | the guard is a literal `"<style>"`; `<style media="print">` walks past it (Finding 5) |
| G9 | **CONFIRMED** | all four landmark slices byte-identical main→HEAD; every landmark unique |

New findings: Finding 3 (viewport yank, medium), Finding 4 (tab focus, low).

---

### G1 — CONFIRMED

`matchesGroupSearch` (index.html:744) splits on `/\s+/` (which in JS also matches NBSP, so a pasted
` ` still separates terms), lowercases both sides, and tests with `String.includes` — no regex ever
sees the query. Returns a boolean only; the row and the echoed query go through `esc()`
(index.html:343–346, which covers `& < > " '`). Measured:

```
rows for 'app-ocp-rbac-*': 0   | no throw
rows for 'a(lpha':          0   | no throw
'"alpha\' <img src=x onerror=alert(1)>' round-trips the value attribute intact | no throw, no XSS
```

The branch's own order/case/AND tests pass in the suite. Cannot refute.

### G2 — FIX-INADEQUATE — medium — index.html#groupsPage (lines 771–777)

The header's `N of M` is honest (M is the state-filtered list the server returned — the endpoint filter
is server-side, `api.py:361–372`), and the normal empty state is fine. But the claim "the empty state
says the search is hiding rows rather than the data being empty" is **false in a reachable state** —
see Finding 2.

### G3 — FIX-INADEQUATE — major — index.html#renderFilters (lines 454–516)

What the claim literally says is true and was measured: capture is by id, `selectionStart` is read
inside a try, focus and caret survive the repaint (`{'focused': True, 'start': 5}` after a forced
`render()` with the caret parked mid-word), a focused `<select>` is restored without a throw
(`selectionStart` on it is `undefined`, and `undefined !== null` falls through to the
`el.setSelectionRange` existence check, so nothing is attempted), a vanished restore target is skipped
silently, and `pageerror` stayed empty through every experiment. But the repaint destroys the one thing
the restore cannot put back — an IME composition — which makes the box unusable for composed input.
That is Finding 1. The restore also introduces a viewport yank (Finding 3, NEW, same machinery).

### G4 — CONFIRMED

`GET /api/clusters/{id}/groups` (api.py:361–372) accepts only `state` and returns
`store.groups(cluster_id, state)` whole — no limit parameter exists. The branch's fetch-counting test
(`test_searching_does_not_refetch`) passes; typing issued zero fetches in my runs too. Cannot refute.

### G5 — CONFIRMED

`test_a_filtered_row_still_drills_in` passes; the row click lands on `view.group ===
'app-ocp-rbac-alpha-ns-admin'` through `navigate()`. Cannot refute.

### G6 — CONFIRMED

Verified end to end in Chromium, two independent ways — Playwright's computed accessible name/
description assertions, and the raw CDP accessibility tree:

```
AX node: searchbox | name: 'Find' | description: 'Filters the group list by name as you type.
Several words are combined with AND, so every word must appear. Press Escape to clear.'
```

No `aria-label` anywhere near the box, so the visible label IS the accessible name (WCAG 2.5.3 holds:
"click Find" hits it). `.sr-only` (app.css) is the 1px-clip pattern, not `display:none` — the branch's
own test asserts computed display and a ≤2px box, and the description above proves the text is in the
tree. The `title` attribute duplicates the help as a mouse tooltip; with `aria-describedby` present it
does not compete for the description. Cannot refute.

### G7 — CONFIRMED

Extracted the `<style>` block from the pre-extraction commit (`c2e3073`) and diffed against `app.css`:
the stylesheet is **byte-identical** except for the 19-line WHY header comment added at the top of
app.css (25 unified-diff lines, all additions at position 0). One `<style>` block existed before; zero
after; the `<link rel="stylesheet" href="/static/app.css">` is in `<head>`. Served:

```
GET /static/app.css -> 200, content-type: text/css; charset=utf-8, 37494 bytes
```

Cannot refute.

### G8 — FIX-INADEQUATE — low — tests/test_type_scale.py:49 (`test_the_stylesheet_stays_out_of_the_page`)

See Finding 5.

### G9 — CONFIRMED

Extracted all four slices exactly as `test_display_timezone.py` takes them
(`function fmtTime`→`\nfunction `, `function setDisplayZone`→`\n/* Absolute time`,
`<th>Day (UTC)</th>`→`</table>`, `function fmtClock`→`\nfunction `) from `main` (1ddaa8e) and from
HEAD, and compared:

```
fmtTime        main: 1610 head: 1610 identical: True
setDisplayZone main:  595 head:  595 identical: True
usage          main:  555 head:  555 identical: True
fmtClock       main:  713 head:  713 identical: True
```

Every landmark occurs exactly once in both versions, so no slice silently widened, narrowed, or
re-anchored — the CSS sat entirely above the first landmark. Cannot refute.

---

### Finding 1

> **Fable:** FIX-INADEQUATE — major — local-development/gsd/static/index.html#renderFilters (oninput at 486, innerHTML swap at 463)

**Trigger.** Focus the search box with any IME active — Japanese/Chinese/Korean, or a macOS dead-key
sequence — and compose. Every composition update fires `input`; `oninput` calls `render()`; the repaint
replaces the node the IME session is bound to. The session aborts, the half-composed text is committed
as literal characters, and the IME's next update opens a *second* session on the replacement node.
Independently, the 30s poll's `render()` does the same to a composition in flight even when `oninput`
is fixed. Measured with CDP `Input.imeSetComposition` — the same Blink path a real OS IME drives:

```
compose か → かん, commit かんり (control, static input): value 'かんり'    ← simulation is sound
same sequence into #f-group-search on this branch:        value 'かかんかんり'
poll render() fired mid-composition (branch):             value 'かかんり'
```

**Consequence for a reader.** The query itself is silently corrupted — the reader typed かんり and the
box searched for かかんかんり — so the table goes empty and the empty state tells them no group matches
a query they never typed. They conclude the group does not exist. The box is unusable for any composed
input, and the 30s timer makes even careful use lose words mid-composition.

**Replacement — three hunks, comments preserved.** (Validated on the scratch copy: composed value
`かんり` in both scenarios, zero pageerrors, all 122 existing UI tests still pass.)

Hunk 1 — module scope, immediately after the `/* ---------- rendering ---------- */` divider
(index.html:374), before `renderFilters`:

```js
/* True while an IME composition is live in the search box. Module-level rather than on the element,
   because the element this bar renders is replaced wholesale — state on the node would vanish with it,
   which is the exact failure this flag exists to prevent. */
let groupSearchComposing = false;
```

Hunk 2 — the capture block (index.html:454–462). Only the comment-plus-guard between `const active = …`
and `let restore = null;` is new; the surrounding comment and code are unchanged:

```js
  const active = document.activeElement;
  // A repaint mid-IME-composition destroys more than focus: the composition session is bound to the
  // NODE, so replacing it commits half-composed kana as literal text and the IME's next update opens a
  // second session on the replacement — typing かんり lands as かかんかんり. No after-the-fact restore
  // can repair that, so while a composition is live in this box the bar keeps its existing DOM and the
  // caller still repaints the data below; the compositionend handler runs the catch-up render.
  if (groupSearchComposing && active === $("f-group-search")) return;
  let restore = null;
  if (active && active.id && $("filters").contains(active)) {
    restore = { id: active.id, start: null, end: null };
    try {
      restore.start = active.selectionStart;
      restore.end = active.selectionEnd;
    } catch (e) { /* not a selectable input; focus alone is enough */ }
  }
```

Hunk 3 — the handlers (index.html:481–496 becomes):

```js
  const gs = $("f-group-search");
  if (gs) {
    // `input`, not `change`: it has to filter as the reader types. render() rather than refresh()
    // because the groups endpoint applies no limit, so the whole list is already here — filtering is a
    // repaint and costs no round trip, and a request per keystroke would be both slower and wrong.
    //
    // Except mid-IME-composition: those input events describe an unfinished conversion, and a repaint
    // here replaces the node the IME is composing into (see the guard above the innerHTML swap). The
    // state still updates, so the compositionend render loses nothing.
    gs.oninput = (e) => {
      view.groupSearch = e.target.value;
      if (!e.isComposing) render();
    };
    // addEventListener, not on-properties: composition events have no IDL handler attribute, so
    // `gs.oncompositionstart = …` is a silent no-op expando — the flag would never be set. The node is
    // freshly created on every rebuild, so listeners never stack on one element.
    gs.addEventListener("compositionstart", () => { groupSearchComposing = true; });
    gs.addEventListener("compositionend", (e) => {
      groupSearchComposing = false;
      view.groupSearch = e.target.value;
      render();
    });
    // compositionend fires before blur in every engine, but a missed one would freeze this bar
    // forever (the guard above would always return), so blur clears the flag as a backstop.
    gs.addEventListener("blur", () => { groupSearchComposing = false; });
    gs.onkeydown = (e) => {
      // Escape clears rather than blurring, which is what a reader expects of a filter box and what
      // type=search does natively on the platforms that render its clear button. Mid-composition it
      // belongs to the IME — cancel the kana, keep the query — so it is left alone.
      if (e.key === "Escape" && !e.isComposing && view.groupSearch) {
        e.preventDefault();
        view.groupSearch = "";
        render();
      }
    };
  }
```

Two honest caveats, both verified as far as the harness allows: (a) the early `return` also skips
`document.body.dataset.page` — reachable mid-composition only via popstate (Back mid-composition), and
the compositionend render catches up one beat later; (b) the `!e.isComposing` Escape guard follows the
UI-Events ordering (keydown during composition carries `isComposing: true`), but CDP cannot reproduce
that ordering — an injected Escape does not route through an IME, so the composition is already
cancelled before the key event dispatches. The two composition tests below are the enforcement that
matters.

**Test — fails on the branch, passes with the fix** (append to `tests/test_ui.py`; measured: both fail
before — `'かかんかんり'`, `'かかんり'` — both pass after):

```python
class TestGroupSearchIme:
    """CJK, and every other composed input, goes through an IME whose composition session is bound to
    the NODE it is composing into. renderFilters replaces that node, so a repaint mid-composition
    commits half-composed kana as literal text and the IME's next update opens a second session:
    typing かんり lands as かかんかんり. CDP's Input.imeSetComposition is a real composition as far as
    Blink is concerned — the same code path a macOS or Windows IME drives."""

    def _open(self, dash):
        dash.locator("button[data-nav='groups']").click()
        dash.wait_for_selector("#f-group-search")
        dash.focus("#f-group-search")
        return dash.context.new_cdp_session(dash)

    def test_an_ime_composition_survives_its_own_input_events(self, dash):
        cdp = self._open(dash)
        cdp.send("Input.imeSetComposition", {"text": "か", "selectionStart": 1, "selectionEnd": 1})
        dash.wait_for_timeout(100)
        cdp.send("Input.imeSetComposition", {"text": "かん", "selectionStart": 2, "selectionEnd": 2})
        dash.wait_for_timeout(100)
        cdp.send("Input.insertText", {"text": "かんり"})
        dash.wait_for_timeout(100)
        got = dash.evaluate("() => document.getElementById('f-group-search').value")
        assert got == "かんり", f"the composition was aborted by a repaint: {got!r}"
        assert dash.evaluate("() => view.groupSearch") == "かんり"

    def test_the_poll_firing_mid_composition_does_not_abort_it(self, dash):
        """The 30s timer cannot be asked to wait for the reader's IME."""
        cdp = self._open(dash)
        cdp.send("Input.imeSetComposition", {"text": "か", "selectionStart": 1, "selectionEnd": 1})
        dash.wait_for_timeout(100)
        dash.evaluate("() => render()")  # exactly what the poll does
        dash.wait_for_timeout(100)
        cdp.send("Input.imeSetComposition", {"text": "かん", "selectionStart": 2, "selectionEnd": 2})
        dash.wait_for_timeout(100)
        cdp.send("Input.insertText", {"text": "かんり"})
        dash.wait_for_timeout(100)
        got = dash.evaluate("() => document.getElementById('f-group-search').value")
        assert got == "かんり", f"the poll's repaint aborted the composition: {got!r}"
```

**Debt: DEBT-INTRODUCED** — the branch put a text input inside an innerHTML-replaced bar; composition
survival is part of the cost of that architecture, not an optional extra.

### Finding 2

> **Fable:** FIX-INADEQUATE — medium — local-development/gsd/static/index.html#groupsPage (lines 771–777)

**Trigger.** Any state filter that matches zero groups (a healthy cluster has no `empty` groups) plus
any text in the search box. `searching` is true, `rows.length === 0`, `all.length === 0`. Measured on
the branch:

```
view.groupFilter='empty'; data.groups=[]; view.groupSearch='admin'
empty-note: "No group name contains admin. 0 groups match the state filter, so it is the search
             hiding them rather than the data being empty."
```

**Consequence for a reader.** The sentence is false in exactly the dimension G2 exists to protect: with
a zero denominator the search hides nothing — the data (under that state filter) IS empty. The reader
clears their query expecting rows, gets none, and has been told the wrong cause. Secondary: with
`all.length === 1` the message reads "1 group match the state filter … hiding them" — wrong verb, wrong
pronoun, in a sentence whose whole job is precision.

**Replacement** (index.html:771–777; validated — zero case now says "No groups match this filter.",
one case says "1 group matches … hiding it", plural case unchanged; branch's own
`test_a_term_matching_nothing…` still passes since it runs with a denominator of 4):

```js
    ${rows.length === 0
      ? (searching && all.length > 0
          // Only blame the search when it IS the search: with a zero denominator the state filter
          // (or the cluster) has nothing to show, and "the search is hiding them" would be false —
          // the reader would clear their query expecting rows and get none.
          ? `<div class="empty-note">No group name contains
              <strong>${esc(view.groupSearch.trim())}</strong>. ${all.length === 1
              ? `1 group matches the state filter, so it is the search hiding it`
              : `${all.length} groups match the state filter, so it is the search hiding them`}
              rather than the data being empty.</div>`
          : `<div class="empty-note">No groups match this filter.</div>`)
```

**Test — fails on the branch, passes with the fix** (append inside the new tests in `tests/test_ui.py`;
measured both ways):

```python
class TestGroupSearchEmptyStateHonesty:
    def _open(self, dash):
        dash.locator("button[data-nav='groups']").click()
        dash.wait_for_selector("#f-group-search")

    def test_a_zero_denominator_does_not_blame_the_search(self, dash):
        """With no groups matching the STATE filter the search hides nothing, so "it is the search
        hiding them" is false — the reader would clear a query that was never the cause and still
        see an empty table."""
        self._open(dash)
        # The shape the server returns for a state filter with no matches, plus an active search.
        dash.evaluate(
            "() => { view.groupFilter = 'empty'; data.groups = []; view.groupSearch = 'admin'; render(); }")
        note = dash.locator(".empty-note").inner_text()
        assert "search hiding" not in note, note
        assert "No groups match this filter" in note, note

    def test_a_denominator_of_one_reads_as_one(self, dash):
        self._open(dash)
        dash.select_option("#f-state", "unattributed")
        dash.wait_for_function("() => data.groups.length === 1")
        dash.fill("#f-group-search", "zzz")
        dash.wait_for_function("() => view.groupSearch === 'zzz'")
        note = " ".join(dash.locator(".empty-note").inner_text().split())
        assert "1 group matches the state filter" in note, note
        assert "the search hiding it rather" in note, note
```

(Aside, not fixed here: the "Filtered by … to see all 0." bar note above the table shares the zero-case
oddity but states no falsehood — "see all 0" is merely clumsy. The arbiter may fold a
`searching && all.length > 0` condition into that note too if wanted; the replacement above deliberately
touches only the lying sentence.)

**Debt: DEBT-INTRODUCED** — the sentence was added by this branch and asserts a falsehood in a
reachable state.

### Finding 3

> **Fable:** NEW — medium — local-development/gsd/static/index.html#renderFilters (line 509, `el.focus()`)

**Trigger.** Click into the search box (focus parks there), scroll down into the groups table — 64 rows
on the reference cluster — and wait for the 30s poll. The restore's bare `el.focus()` scrolls the
filter bar back into view. Measured, with the control that isolates the cause:

```
focus in #f-group-search:  scrollY 214 -> 0     (branch)
focus on body (control):   scrollY 214 -> 214   (branch — render alone does NOT move the viewport)
focus in #f-group-search:  scrollY 214 -> 214   (fixed copy, still focused afterwards)
```

**Consequence for a reader.** Every 30 seconds the page jumps to the top while they are reading rows
below the fold. The reader believes the dashboard reset or reloaded — and loses the row they were
comparing; on a long list they may re-read the top and draw conclusions from the wrong rows.

**Replacement** (index.html:506–516; the only code change is the `focus` call — the caret comment and
logic are untouched):

```js
  if (restore) {
    const el = $(restore.id);
    if (el) {
      // preventScroll: the bar sits at the top of the page, and a bare focus() scrolls it into view —
      // so with focus parked in the search box, every 30s poll would yank a reader who had scrolled
      // into the table back to the top. Focus is being RESTORED here, not moved; the viewport must not
      // know the element was ever replaced.
      el.focus({ preventScroll: true });
      // Put the caret back where it was, rather than at the end: a reader correcting a typo in the
      // middle of a term would otherwise have every subsequent keystroke jump to the end of the field.
      if (restore.start !== null && el.setSelectionRange) {
        try { el.setSelectionRange(restore.start, restore.end); } catch (e) { /* not selectable */ }
      }
    }
  }
```

**Test — fails on the branch (scrollY 214→0), passes with the fix:**

```python
class TestGroupSearchScroll:
    def test_the_poll_does_not_yank_the_viewport_while_the_box_is_focused(self, dash):
        """focus() scrolls its target into view, and the restored box sits at the top of the page —
        so with focus parked in the search box, every poll would jump a reader who had scrolled
        into the table back to the top."""
        dash.locator("button[data-nav='groups']").click()
        dash.wait_for_selector("#f-group-search")
        dash.set_viewport_size({"width": 900, "height": 400})
        dash.focus("#f-group-search")
        dash.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        before = dash.evaluate("() => window.scrollY")
        assert before > 0, "page too short to scroll — shrink the viewport further"
        dash.evaluate("() => render()")  # the 30s poll
        after = dash.evaluate("() => window.scrollY")
        assert after == before, f"the repaint scrolled the page from {before} to {after}"
        assert dash.evaluate(
            "() => document.activeElement === document.getElementById('f-group-search')")
```

**Debt: DEBT-INTRODUCED** — the restore machinery is new in this branch, and the yank arrives with it.

### Finding 4

> **Fable:** NEW — low — local-development/gsd/static/index.html#renderFilters (tab template, lines 433–434)

**Trigger.** A keyboard user tabs onto a nav tab ("Groups", say) and pauses; the 30s poll repaints the
bar. The restore captures by `active.id`, and the tab buttons have none — so focus drops to `<body>`.
Measured: `focused before: groups` → `activeElement after poll repaint: BODY`. (Pre-existing in the
sense that main restored nothing at all; this branch built the restore and covered only id-carrying
elements, so the one control type left out is the one keyboard users rest on longest.)

**Consequence for a reader.** Their keyboard position silently evaporates on a timer; the next Tab
press starts from the top of the document. Nothing false is displayed — this is a usability loss, hence
low.

**Replacement** (index.html:431–434; ids `tab-*` collide with nothing — checked both files):

```js
  // aria-current, not just a class: it is what tells a screen reader which section is
  // open. The visual bar and the bolder label are the sighted half of the same signal.
  //
  // The id exists for the focus restore below, which finds elements by id alone — without it a
  // keyboard user resting on a tab is dropped to <body> by every 30s repaint, losing their place
  // in the tab order.
  const tab = (id, label) =>
    `<button class="tab" id="tab-${id}" data-nav="${id}"${view.page === id ? ' aria-current="page"' : ""}>${label}</button>`;
```

(`selectionStart` on a button is `undefined` and `setSelectionRange` absent, so the existing restore
handles it without a throw — same measured path as the `<select>`.)

**Test — fails on the branch (focus fell to None), passes with the fix:**

```python
class TestTabFocusSurvivesTheRepaint:
    def test_a_keyboard_user_resting_on_a_tab_keeps_it_across_the_poll(self, dash):
        """The restore machinery finds elements by id, and the nav tabs had none — so the reader who
        tabbed to "Groups" and paused was silently dropped to <body> by the next poll."""
        dash.focus("button[data-nav='groups']")
        dash.evaluate("() => render()")  # the 30s poll
        got = dash.evaluate("() => document.activeElement.dataset && document.activeElement.dataset.nav")
        assert got == "groups", f"focus fell to {got!r} when the filter bar re-rendered"
```

**Debt: DEBT-ACCEPTED** — the focus loss predates the branch; the branch built the machinery that makes
closing it a two-token change, and should.

### Finding 5

> **Fable:** FIX-INADEQUATE — low — local-development/tests/test_type_scale.py:49 (`test_the_stylesheet_stays_out_of_the_page`)

**Trigger.** Re-inline a style block with any attribute on the tag — `<style media="print">` is the
plausible, legitimate-looking one (print styles "just for this page"). Measured:

```
current guard ('<style>' not in page) passes the evaded page: True
regex guard (r'<style\b', re.I) catches it:                    True
regex on the pristine page:                                    False
```

**Consequence for a reader** — of the test suite, which is also a reader of this dashboard's
guarantees: green tests say "every rule is contrast- and scale-checked", while a media- or
type-attributed inline block renders on the page unchecked by either. Exactly the invisible bypass G8
claims is now impossible.

**Replacement** (`import re` already exists at test_type_scale.py:18; docstring extended, not
replaced):

```python
def test_the_stylesheet_stays_out_of_the_page():
    """No inline <style> in index.html, so nothing can escape the two checks that read app.css.

    The failure this prevents is quiet: a rule added inline still renders, so the page looks right while
    its font-size skips the scale and its colours skip the contrast check.

    A regex on the open tag, not a literal "<style>": any attribute — <style media="print"> is the
    plausible one — would make the literal miss a block the browser still applies.
    """
    page = INDEX.read_text()
    assert not re.search(r"<style\b", page, re.I), (
        "index.html has an inline <style> block again. The type scale and the WCAG contrast checks read "
        "gsd/static/app.css, so anything inline is invisible to both. Move it to app.css."
    )
    assert '<link rel="stylesheet" href="/static/app.css">' in page, (
        "index.html no longer links the stylesheet — the page would render unstyled"
    )
```

**Test.** This IS the test; on the pristine tree it passes before and after (nothing inline exists),
and on the defect it detects — a `<style media="print">` block inserted into index.html — the current
assertion passes (the bug) while the replacement fails (the fix). Demonstrated above with both
predicates run against the same evaded page.

**Debt: DEBT-ACCEPTED** — the guard is new and closes the big hole; this narrows the remaining one to
zero for one line of regex.

---

### Verdict on the branch

The feature's core claims hold up under measurement — the matcher is literal and correct (G1), the
denominator honest in the common case (G2), the search costs no network (G4), drill-in survives (G5),
the accessibility pattern is textbook and verified in the real AX tree (G6), and the CSS extraction is
byte-exact, served correctly, and disturbed none of the landmark-sliced tests (G7, G9). What fails is
the corner the repaint architecture was always going to be graded on: the innerHTML-replace-plus-restore
approach preserves focus and caret but not an IME composition (Finding 1 — the box silently corrupts
composed queries into garbage like かかんかんり, then tells the reader no group matches), the restored
`focus()` yanks the viewport to the top on every poll for anyone reading below the fold (Finding 3), and
the empty state tells a reachable lie when the state filter's own denominator is zero (Finding 2). I
would not merge as it stands: apply Findings 1–3 first — all three replacements are written, validated
in a live browser against a scratch copy, and pass the full 122-test UI suite plus the 6 new tests.
**Fix Finding 1 first**: it is the only one that corrupts what the reader typed and then uses the
corruption to tell them something false about the data, and it takes Finding 3's one-line
`preventScroll` and Finding 4's tab ids along in the same function. Findings 4 and 5 are cheap
follow-ons that can ride the same commit.

## Arbitration

Every finding was verified independently before it was applied. Verdicts, and the evidence behind each.

### Applied — 6 of Fable's 6

| # | Verdict | What I verified myself, before applying |
|---|---|---|
| **1** IME corruption | **APPLIED** | Reproduced: typing `かんり` into the box landed `かかんかんりかんり`. Proved the repaint is the cause, not the IME harness, by composing the same text into a static control input on the same page — clean. Also verified the fix's mechanism is load-bearing: `gs.oncompositionstart = fn` fires **0** times (composition events have no IDL handler attribute, so the assignment is an inert expando), `addEventListener` fires **1**. A fix written with the property form would have looked right and done nothing. |
| **2** empty state lies | **APPLIED** | Reproduced against `prod-east`, which carries 0 groups: the note claimed "0 groups match the state filter, so it is the search hiding them". Also fixed the singular grammar Fable flagged — "1 group matches … hiding **it**". |
| **3** `focus()` scrolls | **APPLIED** | Measured `scrollY` across a forced repaint with focus in the box: `214 → 0` before, `214 → 214` after. |
| **4** tabs lack ids | **APPLIED** | The restore finds elements by id alone, so a keyboard user resting on a tab was dropped to `<body>` every 30s. After: focus lands on `BUTTON/tab-groups`. |
| **5** `<style>` regex | **APPLIED** | `<style media="print">` defeats a literal `"<style>" not in page` while the browser still applies the block. `re` was already imported in that module. |
| — | — | All six re-verified in a real browser afterwards: IME clean (including under a forced mid-composition `render()`), caret preserved (`focused=True caret=5`), no uncaught JS errors. |

### Found by my own second pass — not by Fable, not by me the first time

**The banner made the same false claim as the empty state, six lines above it.** Fable's Finding 2 named
the empty note; I fixed the empty note. The banner at `groupsPage` said *"Clear the box, or press Escape
in it, to see all 0"* whenever the state filter's denominator was zero — an instruction that produces the
same empty table. One defect stated in two places, and fixing the site the review named left the other
one live.

The lesson is the reusable part: **a finding names a symptom, not its blast radius.** Before calling a
finding closed, grep for every site that states the same fact. Two tests now cover it — one that the
banner drops the offer at a zero denominator, one that it still makes the offer when there is exactly
one group, so the guard cannot over-suppress. The first — `test_the_banner_does_not_promise_rows_that_do_not_exist`
— fails on the pre-fix file, which is how I know it tests something.

### Structural audit of my own splices

The PR #12 arbitration produced five splicing mistakes, so the same audit ran here before commit:

```
JS functions : 53 -> 53   MISSING: none   added: none
CSS tokens   : 45 -> 45   MISSING: none
script braces balanced: True  (785/785)
no conflict markers: True    no inline <style>: True
```

The early return added to `renderFilters` skips the handler rebinding for **every** tab's filter bar, not
just the search box, so all seven tabs were exercised in a browser: each renders, `aria-current` lands on
the right id, `f-state` / `f-cluster` / `f-binding` all still drive `view`, and no tab raises a JS error.
That is the regression this fix could plausibly have caused, and it did not.

### Suite

`1058 passed, 1 skipped` — 1050 on the branch before this work, plus 8 new tests (6 for Fable's findings,
2 for the banner). Fable's report cites a 1049 baseline; the doc's stated figure was off by one.

### Not done

A third review pass over `parse()` and `fetch_pod_log` in the login-capture module. Fable's replacements
shipped there in 6 of 11 places on my verification alone, without a second reviewer disagreeing with
them. That is the largest piece of unreviewed logic in the merged PR and it is out of this branch's scope.
