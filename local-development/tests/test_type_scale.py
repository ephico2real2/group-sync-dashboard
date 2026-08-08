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
    """
    page = INDEX.read_text()
    assert "<style>" not in page, (
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
