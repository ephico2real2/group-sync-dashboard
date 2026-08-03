"""WCAG 2.1 AA contrast, computed from the stylesheet rather than eyeballed.

This started as a throwaway script and found NINE failures in the shipped UI — the worst
being --text-muted at 3.41:1, which colours table headers, KPI labels, axis text and every
empty state. It belongs in the repo: without it the next well-meant colour tweak silently
undoes the fix, and a contrast regression is invisible in review.

Section 508 conformance for web content means WCAG 2.1 Level AA:
  1.4.3  normal text            4.5:1
         large text (>=24px, or >=18.66px bold)   3:1
  1.4.11 non-text UI components and graphical objects   3:1

The required ratio is chosen PER USE, not per token. --status-warning is only ever a badge
glyph, so it is a graphical object at 3:1 — held to 4.5:1 an amber turns brown and stops
reading as a warning at all. --status-good and --status-critical are both a glyph AND
running text, so both are held to the text bar.
"""

from __future__ import annotations

import pathlib
import re

import pytest

INDEX = pathlib.Path(__file__).resolve().parents[1] / "gsd" / "static" / "index.html"

AA_TEXT = 4.5
AA_LARGE_OR_GRAPHIC = 3.0


def _linear(channel: float) -> float:
    c = channel / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_colour: str) -> float:
    """WCAG 2.1 relative luminance."""
    h = hex_colour.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b)


def ratio(foreground: str, background: str) -> float:
    a, b = luminance(foreground), luminance(background)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def _block(css: str, pattern: str) -> dict[str, str]:
    match = re.search(pattern, css, re.S)
    assert match, f"could not find the token block {pattern!r} — did the stylesheet move?"
    return dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{3,8})\s*;", match.group(1)))


@pytest.fixture(scope="module")
def themes():
    css = INDEX.read_text()
    light = _block(css, r":root\s*\{(.*?)\n\}")
    # The dark block only overrides what changes; the rest cascades from :root.
    dark = {**light, **_block(css, r':root\[data-theme="dark"\]\s*\{(.*?)\n\}')}
    return {"light": light, "dark": dark}


# (token, background token, required ratio, why)
TEXT_ON_PAGE = [
    ("text-primary", "page", AA_TEXT, "body copy"),
    ("text-secondary", "page", AA_TEXT, "secondary copy"),
    ("text-muted", "page", AA_TEXT, "table headers, KPI labels, axis text, empty states"),
]
TEXT_ON_CARD = [
    ("text-primary", "surface-1", AA_TEXT, "body copy on a card"),
    ("text-secondary", "surface-1", AA_TEXT, "secondary copy on a card"),
    ("text-muted", "surface-1", AA_TEXT, "muted copy on a card"),
    ("status-good", "surface-1", AA_TEXT, ".change-added"),
    ("status-critical", "surface-1", AA_TEXT, ".change-removed and .err"),
    ("series-1", "surface-1", AA_TEXT, ".drill and .back link text"),
]
GRAPHICAL = [
    ("status-warning", "surface-1", AA_LARGE_OR_GRAPHIC, "badge glyph only, never text"),
    *[(f"series-{i}", "surface-1", AA_LARGE_OR_GRAPHIC, f"owner dot / chart mark {i}")
      for i in range(1, 9)],
]
# Active tab labels sit on the page; the accent also tints a card edge and the hero numeral.
# Derived from the stylesheet, not hardcoded: a hardcoded list silently stops covering a
# new tab, which is exactly what happened when `policy` and `nsaudit` were added — the
# suite stayed green while two accents went unchecked.
def _tab_tokens(css: str) -> list[str]:
    return sorted(set(re.findall(r"--(tab-[a-z]+):", css)))


TAB_NAMES = _tab_tokens(INDEX.read_text())
TABS = [(token, "page", AA_TEXT, f"active {token} label") for token in TAB_NAMES]


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize(
    "token,background,required,why",
    TEXT_ON_PAGE + TEXT_ON_CARD + GRAPHICAL + TABS,
    ids=lambda v: v if isinstance(v, str) else str(v),
)
def test_contrast(themes, theme, token, background, required, why):
    tokens = themes[theme]
    assert token in tokens, f"--{token} is missing from the {theme} theme"
    got = ratio(tokens[token], tokens[background])
    assert got >= required, (
        f"{theme}: --{token} ({tokens[token]}) on --{background} ({tokens[background]}) "
        f"is {got:.2f}:1, below the {required} required for {why}"
    )


def test_the_known_regressions_stay_fixed(themes):
    """Named explicitly so a future palette change cannot quietly reintroduce them.

    Each of these shipped below the bar and was corrected by moving HSL lightness the
    minimum distance to clear it, holding hue and saturation exactly.
    """
    was_broken = [
        ("light", "text-muted", "page", 3.41),
        ("light", "status-good", "surface-1", 3.27),
        ("light", "series-1", "surface-1", 4.30),
        ("light", "series-3", "surface-1", 2.74),
        ("light", "series-4", "surface-1", 2.11),
        ("light", "series-5", "surface-1", 2.62),
        ("dark", "status-critical", "surface-1", 3.62),
    ]
    for theme, token, background, previously in was_broken:
        tokens = themes[theme]
        now = ratio(tokens[token], tokens[background])
        assert now > previously, (
            f"{theme} --{token} is back at {now:.2f}:1, at or below the {previously}:1 "
            f"it shipped at before the accessibility pass"
        )
