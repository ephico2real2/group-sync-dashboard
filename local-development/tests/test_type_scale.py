"""The type scale is a scale, not a pile of numbers.

An audit of the shipped stylesheet counted TEN distinct font-size values, every one of them
chosen at the call site with no ladder connecting them. That is how an interface comes to
read as assembled rather than designed, and it is self-worsening: with no named scale there
is nothing for the next size to be inconsistent *with*, so an eleventh arrives unnoticed and
review has no ground to object from.

The ten were not wrong, so nothing moved — they were named. What this file adds is the part
that makes naming stick: a size that is not one of the tokens fails the suite. Adding a step
is fine and takes one line; adding it by accident is not.

Companion to test_accessibility.py, which guards the colour tokens the same way.
"""

from __future__ import annotations

import pathlib
import re

import pytest

STATIC = pathlib.Path(__file__).resolve().parents[1] / "gsd" / "static"
INDEX = STATIC / "index.html"
CSS = STATIC / "app.css"


@pytest.fixture(scope="module")
def css() -> str:
    """The stylesheet, read as a FILE.

    It used to be sliced out of index.html with a `<style>(.*?)</style>` regex, and that assert's
    message asked "did the stylesheet move out of index.html?" — it since has. Reading the file is both
    simpler and stricter: a regex over the page would silently check only the FIRST block if a second
    one were ever added, whereas test_the_stylesheet_stays_out_of_the_page below fails if any inline
    block appears at all.
    """
    assert CSS.exists(), f"{CSS} is missing — the stylesheet is served from /static/app.css"
    return CSS.read_text()


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


@pytest.fixture(scope="module")
def scale(css: str) -> dict[str, int]:
    """The --text-* tokens, read from the stylesheet rather than duplicated here.

    Hardcoding the expected list is what let the accessibility suite stay green while two
    new tab accents went unchecked; the scale is derived for the same reason.
    """
    found = dict(re.findall(r"--text-([a-z0-9]+):\s*(\d+)px\s*;", css))
    assert found, "no --text-* scale tokens found"
    return {name: int(px) for name, px in found.items()}


def test_scale_is_defined(scale):
    """A scale needs enough steps to be usable and few enough to be a scale."""
    assert 5 <= len(scale) <= 12, (
        f"{len(scale)} type steps. Below ~5 the scale cannot express hierarchy; above ~12 "
        f"it has stopped constraining anything: {sorted(scale.values())}"
    )


def test_no_literal_font_sizes(css):
    """Every font-size comes from the scale.

    The failure this prevents is not ugliness, it is drift: one `font-size: 15px` at a call
    site is invisible in review, and the tenth is why the audit happened.
    """
    literals = re.findall(r"font-size:\s*(\d+(?:\.\d+)?)(px|rem|em)\b", css)
    assert not literals, (
        "font-size must use a --text-* token, not a literal. Found: "
        + ", ".join(f"{v}{u}" for v, u in literals)
        + ". Reuse a step, or add one to the scale in :root deliberately."
    )


def test_font_shorthand_does_not_smuggle_a_size(css):
    """`font: 14px/1.5 ...` sets a size while dodging the check above.

    It is also a reset: the shorthand clears line-height, weight and family if omitted, so
    a later edit that drops one silently changes three things.
    """
    smuggled = re.findall(r"font:\s*[^;]*?\d+(?:px|rem|em)[^;]*;", css)
    assert not smuggled, (
        "the `font:` shorthand carries a literal size — split it into font-family, "
        f"font-size: var(--text-*) and line-height. Found: {smuggled}"
    )


def test_every_step_is_used(css, scale):
    """A step nothing references is a decision nobody made.

    Catches both halves of drift: a size defined and then abandoned, and a rename that
    updated the definition but not the call sites.
    """
    unused = [f"--text-{name} ({px}px)" for name, px in scale.items()
              if f"var(--text-{name})" not in css]
    assert not unused, (
        "type steps defined but never used: " + ", ".join(unused)
        + ". Remove them, or use them — an unreferenced token is not a scale, it is a guess."
    )


def test_steps_are_distinct(scale):
    """Two names for one size means the call sites disagree about which to reach for."""
    seen: dict[int, str] = {}
    for name, px in sorted(scale.items(), key=lambda kv: kv[1]):
        assert px not in seen, (
            f"--text-{name} and --text-{seen[px]} are both {px}px. One size, one name — "
            f"otherwise the choice between them is a coin flip that review cannot check."
        )
        seen[px] = name



def test_inline_styles_carry_no_literal_at_all():
    """#152: the page had 92 style= attributes, 24 of them font sizes the stylesheet's scale check
    could not see. Every one is a class now. The one inline style allowed is a value the page can
    only know at render time — a token reference (`background:var(--series-N)`) — never a number."""
    page = INDEX.read_text()
    styles = re.findall(r'style="([^"]*)"', page)
    offenders = [v for v in styles if not re.fullmatch(r"[a-z-]+:var\(--[a-z0-9${}-]+\)(;[a-z-]+:var\(--[a-z0-9${}-]+\))*", v)]
    assert not offenders, (
        "inline style= attributes with a literal value — promote them to a class on the token system: "
        + ", ".join(offenders)
    )


def _declarations(css: str, props: str):
    """(line, property, value) for every declaration of the named properties, comments stripped."""
    for line in css.splitlines():
        code = re.sub(r"/\*.*?\*/", "", line)
        for prop, value in re.findall(rf"(?<![-a-z])({props}):\s*([^;{{}}]+)", code):
            yield line, prop, value.strip()


@pytest.mark.parametrize("props,ladder", [
    ("padding|padding-top|padding-right|padding-bottom|padding-left|gap|row-gap|column-gap|margin|margin-top|margin-right|margin-bottom|margin-left", "--space-"),
    ("border-radius", "--radius-"),
])
def test_spacing_and_radius_come_from_the_ladders(css, props, ladder):
    """#152: a px value in these properties is either a ladder step (var(--space-N) / var(--radius-*))
    or a literal the sheet argues for on the same line with an `optical:` note. The type scale's
    rule, applied to the two other scales the sheet now has."""
    offenders = [line.strip() for line, _, value in _declarations(css, props)
                 if re.search(r"\d+px", value) and "optical:" not in line]
    assert not offenders, (
        f"px literals off the {ladder} ladder without an optical note:\n  " + "\n  ".join(offenders)
    )


def test_ladders_are_defined_and_used(css):
    space = re.findall(r"--space-(\d+):\s*(\d+)px", css)
    radius = re.findall(r"--radius-([a-z]+):\s*([0-9.%px]+)", css)
    assert [int(n) for n, _ in space] == list(range(1, len(space) + 1)), "the spacing ladder skips a step"
    assert [int(px) for _, px in space] == sorted(int(px) for _, px in space), "the spacing ladder is not ascending"
    assert radius, "no radius tokens"
    unused = [f"--space-{n}" for n, _ in space if f"var(--space-{n})" not in css] + \
             [f"--radius-{n}" for n, _ in radius if f"var(--radius-{n})" not in css]
    assert not unused, "ladder steps nothing references: " + ", ".join(unused)


def _token_block_bodies(css: str) -> list[str]:
    """Bodies of the :root / theme / palette rules only. Single-level (`[^}]*`): the first cut ran
    each match to the next INDENTED `}`, and a palette block closing at column 0 swallowed the whole
    `body {}` rule that followed — a hex on body was invisible (Grok, review of #179)."""
    code = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return re.findall(r"^[ ]{0,2}:root[^\n{]*\{([^}]*)\}", code, re.M)


def _raw_colours_outside_the_tokens(css: str) -> list[str]:
    blocks = _token_block_bodies(css)
    assert blocks, "no :root token blocks found"
    outside = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for b in blocks:
        outside = outside.replace(b, "")
    return [m.group(0).strip() for m in re.finditer(r"^.*#[0-9a-fA-F]{3,8}\b.*$", outside, re.M)
            if "url(" not in m.group(0)]


def test_no_raw_colour_outside_the_token_blocks(css):
    """#152: a hex colour outside :root / the theme blocks / the palette blocks opts that rule out of
    both the appearance and the palette mechanism — the page would keep a light-theme colour on
    a dark page. Colours are tokens; rules reference them."""
    offenders = _raw_colours_outside_the_tokens(css)
    assert not offenders, "raw colours outside the token blocks:\n  " + "\n  ".join(offenders)


@pytest.mark.parametrize("rule", ["body {", ".badge {", "header.top {"])
def test_a_hex_outside_the_tokens_is_seen(css, rule):
    """The guard must see a leak wherever it lands — body is the realistic one (the page text
    colour); the first-cut finder caught .badge and missed body."""
    assert rule in css
    poisoned = css.replace(rule, rule + "\n  color: #ff00ff;", 1)
    assert any("#ff00ff" in o for o in _raw_colours_outside_the_tokens(poisoned)), f"a #hex in {rule!r} was invisible to the guard"


def test_markup_does_not_repeat_the_class_attribute():
    """A second class= on one tag is dropped by the HTML parser, so the utility never applies — the
    bindings search note shipped as class="filterbar-note" … class="mt-3" (Grok, review of #179)."""
    page = INDEX.read_text()
    dupes = re.findall(r"<[^>\n]*\bclass=\"[^\"]*\"[^>\n]*\bclass=\"", page)
    assert dupes == [], "merge the class attributes; the second is dropped: " + ", ".join(dupes)


def test_comments_do_not_nest(css):
    """CSS comments do not nest: a `*/` written inside a comment closes it there, and whatever follows
    is parsed as a broken declaration that swallows the next real one. Measured on #152's first cut:
    a token-block comment quoted `/* optical: … */`, the inner closer ended the comment, and the text
    after it ate `--space-1: 2px;` — every chip lost its padding while the regex-based guards stayed
    green. The render check caught it; this makes the parser's reading the test's reading. (Deleted by
    a careless slice in the Grok pass and restored by OB1's — the self-check below keeps it here.)"""
    nested = [m.group(0)[:120] for m in re.finditer(r"/\*(.*?)\*/", css, re.S) if "/*" in m.group(1)]
    assert not nested, "a comment contains a comment opener — its closer ends the outer comment early: " + " | ".join(nested)


def test_a_nested_comment_opener_is_seen(css):
    """The guard must fire on the first-cut shape: a token-block comment that quotes `/* optical: … */`."""
    poisoned = css.replace("`optical:` note", "`/* optical: … */` note", 1)
    assert poisoned != css
    with pytest.raises(AssertionError):
        test_comments_do_not_nest(poisoned)


def test_a_single_ladder_step_is_written_as_its_token(css):
    """Review of #218 (OB3): an `optical:` note argues for a literal OFF the ladder. A declaration whose
    whole value is one px figure that IS a ladder step (`margin-top: 2px` = --space-1) is not optical,
    it is the token unspelled — the drift the ladder exists to prevent (the frontend-design skill:
    promote hard-coded values). Shorthands mixing an off-ladder figure with a step are left to the
    existing rule."""
    space = {int(px) for _, px in re.findall(r"--space-(\d+):\s*(\d+)px", css)}
    props = ("padding|padding-top|padding-right|padding-bottom|padding-left|gap|row-gap|column-gap"
             "|margin|margin-top|margin-right|margin-bottom|margin-left")
    offenders = [line.strip() for line, _, value in _declarations(css, props)
                 if re.fullmatch(r"(\d+)px", value) and int(value[:-2]) in space]
    assert not offenders, "a ladder step spelled as a literal:\n  " + "\n  ".join(offenders)


def test_every_report_shell_class_the_page_writes_has_a_rule(css: str) -> None:
    """Review of #222 (Codex): `rp-count-live` was written into the Subject scope's markup with no rule
    behind it, so the live count missed the mock's mono/accent treatment and nothing said so. The
    report shell's classes carry an `rp-` prefix (a collision with `.num`/`.scope` once made rows
    unclickable), which makes them cheap to guard: one written into the page without a selector in the
    stylesheet is a class that styles nothing."""
    html = INDEX.read_text()
    written: set[str] = set()
    for value in re.findall(r'class="([^"]*)"', html):
        written.update(re.findall(r"\brp-[A-Za-z0-9_-]+\b", value))
    styled = set(re.findall(r"\.(rp-[A-Za-z0-9_-]+)\b", css))
    assert written, "the report shell's rp- classes are gone from index.html"
    assert written - styled == set(), f"written into the page, styled nowhere: {sorted(written - styled)}"


def test_the_heading_ladder_carries_its_weight_and_tracking(css):
    """#253 via the review of #256 (Codex C5, Cursor finding 1): this module checked sizes, spacing
    and radii and said nothing about `font-weight` or `letter-spacing` — so the ladder change it was
    meant to protect passed because the guard was not looking.

    The ladder is one global rule plus a per-level tracking step, and it exists because
    `.home .answer h1` shipped w700/-0.02em since #158 while every other heading sat at w600 with no
    tracking at all, and the tracking that did exist applied only under `.card >`, so the same `h2`
    looked different depending on where it sat."""
    ladder = re.search(r"h1,\s*h2,\s*h3\s*\{([^}]*)\}", css)
    assert ladder, "the one global heading rule is gone — the ladder is back to per-scope tracking"
    assert re.search(r"font-weight:\s*700", ladder.group(1)), ladder.group(1)
    assert re.search(r"letter-spacing:\s*-0\.01em", ladder.group(1)), ladder.group(1)

    for selector, tracking in (("h1", "-0.02em"), ("h2", "-0.015em")):
        rule = re.search(rf"\n{selector}\s*\{{([^}}]*)\}}", css)
        assert rule and tracking in rule.group(1), f"{selector} lost its optical tracking: {rule}"

    # The per-scope duplication is what made one h2 differ from another; if it comes back, the
    # ladder is no longer the single source and this test is the place that says so.
    for stale in (r"\.card\s*>\s*h2\s*\{[^}]*letter-spacing", r"\.card\s*>\s*h3\s*\{[^}]*letter-spacing"):
        assert not re.search(stale, css), f"per-scope heading tracking is back: {stale}"
