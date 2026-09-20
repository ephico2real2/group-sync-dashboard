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

# The stylesheet is its own file now, not a <style> block in the page. Reading it directly means this
# check cannot be fooled by a second inline block; tests/test_type_scale.py asserts there is none.
CSS = pathlib.Path(__file__).resolve().parents[1] / "gsd" / "static" / "app.css"

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


PALETTES = ("default", "deuter", "protan", "trit", "contrast")


def _composite(over: tuple[float, float, float], alpha: float, under: str, theme: str) -> str:
    """Source-over compositing of a translucent colour on an opaque one, as the browser paints a zebra
    or hovered cell: a*over + (1-a)*under per channel — rounded AWAY from the theme's text, not to the
    nearest value. Chromium quantises the alpha to 8 bits and truncates the blend (measured on the
    seeded page, OB3's review of #204: the light 10 % wash over #fcfcfb paints #e6eef6 where round()
    says #e7eef7), so a token solved to the nearest-rounded surface can land one 8-bit step short of the
    bar on the pixel a reader sees (light/deuter --status-good #0071b0: 4.51 by round(), 4.49 painted).
    Every text token is darker than every surface in the light theme and lighter in the dark one, so the
    worst case is floor() in light and ceil() in dark; a value that clears the bar here clears it under
    either rounding."""
    import math
    rnd = math.floor if theme == "light" else math.ceil
    return "#%02x%02x%02x" % tuple(min(255, max(0, rnd(alpha * c + (1 - alpha) * u)))
                                  for c, u in zip(over, _rgb(under)))


def _wash_fraction(css: str, theme: str, token: str) -> float:
    """The N of `--token: color-mix(in srgb, var(--x) N%, transparent)` in the theme's own block."""
    block = re.search(r':root\[data-theme="dark"\]\s*\{(.*?)\n\}', css, re.S).group(1) if theme == "dark" \
        else re.search(r":root\s*\{(.*?)\n\}", css, re.S).group(1)
    m = re.search(rf"--{token}:\s*color-mix\(in srgb,\s*var\(--[a-z0-9-]+\)\s*(\d+(?:\.\d+)?)%", block)
    assert m, f"--{token} is not a color-mix wash in the {theme} block"
    return float(m.group(1)) / 100


def _rgba(css: str, theme: str, token: str) -> tuple[float, float, float, float]:
    """A translucent token (`--zebra: rgba(r, g, b, a)`) from the theme's block — the light block for
    "light", the explicit dark block for "dark" (its OS-dark twin is held identical by
    test_the_os_dark_palette_twins_match)."""
    block = re.search(r":root\s*\{(.*?)\n\}", css, re.S) if theme == "light" \
        else re.search(r':root\[data-theme="dark"\]\s*\{(.*?)\n\}', css, re.S)
    assert block, f"no token block for {theme}"
    m = re.search(rf"--{token}:\s*rgba\((\d+),\s*(\d+),\s*(\d+),\s*([0-9.]+)\)", block.group(1))
    assert m, f"--{token} is not an rgba() in the {theme} block — the row-surface maths assumes it is"
    return tuple(float(v) for v in m.groups())


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    h = hex_colour.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _over(rgba: tuple[float, float, float, float], under: str) -> str:
    """Source-over compositing of a translucent colour on an opaque one, as the browser paints a
    zebra cell: result = a*over + (1-a)*under, per channel, rounded to the nearest 8-bit value."""
    r, g, b, a = rgba
    return "#%02x%02x%02x" % tuple(round(a * c + (1 - a) * u) for c, u in zip((r, g, b), _rgb(under)))




def _palette_block(css: str, theme: str, palette: str) -> dict[str, str]:
    """The tokens a palette overrides for one theme (#152). Light palettes are `:root[data-palette]`;
    dark ones are the explicit `:root[data-theme="dark"][data-palette]` block — the OS-dark twin
    inside the media query is held identical to it by test_the_os_dark_palette_twins_match."""
    if palette == "default":
        return {}
    if theme == "light":
        return _block(css, rf':root\[data-palette="{palette}"\]\s*\{{(.*?)\n\}}')
    return _block(css, rf':root\[data-theme="dark"\]\[data-palette="{palette}"\]\s*\{{(.*?)\n\}}')


@pytest.fixture(scope="module")
def themes():
    """Every theme × palette combination, keyed "light", "dark", "light/deuter", "dark/contrast", …
    The dark block only overrides what changes; the rest cascades from :root — and a palette
    overrides only the hues it names, on top of its theme."""
    css = CSS.read_text()
    light = _block(css, r":root\s*\{(.*?)\n\}")
    dark = {**light, **_block(css, r':root\[data-theme="dark"\]\s*\{(.*?)\n\}')}
    out = {"light": light, "dark": dark}
    for theme, base in (("light", light), ("dark", dark)):
        for palette in PALETTES[1:]:
            # The unconditional `:root[data-palette]` block matches DARK roots too, at the same specificity
            # as the dark base and later in the sheet, so a dark variant inherits every light-palette
            # token its own dark block does not restate (#204 review: a palette `--warn` leaked into dark).
            leak = _palette_block(css, "light", palette) if theme == "dark" else {}
            out[f"{theme}/{palette}"] = {**base, **leak, **_palette_block(css, theme, palette)}
    # THE ROW SURFACES, COMPOSITED (#184). A table cell is not the card: zebra rows lay --zebra
    # (translucent) over --surface-1, and a hovered .rowlink lays --series-1-wash — color-mix(in srgb,
    # var(--series-1) 10%, transparent) — over it. Text in those cells is read against the composed
    # colour, and the drill link that passed 4.55:1 on the card measured 4.32 on zebra and 3.99 on
    # hover. Two pseudo-tokens per variant, computed from the stylesheet the same way the browser
    # composites them, so the bar is held where the text actually is.
    for key, tokens in out.items():
        theme = key.split("/")[0]
        r, g, b, a = _rgba(css, theme, "zebra")
        tokens["row-zebra"] = _composite((r, g, b), a, tokens["surface-1"], theme)
        # --series-1-wash's own percentage, per theme: 10 % light, 14 % dark. Hard-coded at 10 % for both,
        # the dark hover surface here was lighter than the one the browser paints and the dark status
        # text passed at 4.5 while measuring 4.29-4.39 on the real row (#204 review).
        tokens["row-hover"] = _composite(_rgb(tokens["series-1"]), _wash_fraction(css, theme, "series-1-wash"), tokens["surface-1"], theme)
    return out


VARIANTS = ["light", "dark"] + [f"{t}/{p}" for t in ("light", "dark") for p in PALETTES[1:]]


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
    ("drill-text", "surface-1", AA_TEXT, ".drill and .back link text"),
]
GRAPHICAL = [
    ("status-warning", "surface-1", AA_LARGE_OR_GRAPHIC, "badge glyph only, never text"),
    *[(f"series-{i}", "surface-1", AA_LARGE_OR_GRAPHIC, f"owner dot / chart mark {i}")
      for i in range(1, 9)],
]
# td.num.warn is text at weight 600 (#152 defined the token the Users tab had been referencing
# through a hard-coded fallback), so it is held to the text bar, unlike the badge amber.
WARN_TEXT = [("warn", "surface-1", AA_TEXT, "td.num.warn"), ("warn", "page", AA_TEXT, "td.num.warn on a bare row")]
# Text that lives in table cells is held to the bar on the composed ROW surfaces, not only the card
# (#184): the link on a zebra row and on a hovered row, the muted chevron and .change-baseline beside
# it, and the body/secondary copy every cell carries. These are the pairs that were never checked.
# The status tokens (.change-added, .change-removed, td.num.warn) joined the list with #204: measured
# on 2026-09-19 with these same surfaces they failed 4.5 on the rows in eight of the ten theme x
# palette variants (31 pairs, 3.96-4.44; light/contrast only through --warn, which no palette
# overrode); every block was re-tuned by the smallest hue-preserving step that clears the bar on the
# hovered row (the worst surface) toward black (light) or white (dark) — the dark ones against the
# 14 % wash the dark sheet really paints, and all of them against the compositor's own truncation
# (the review of #204 caught both: the fixture's 10 % for both themes, and round() where Chromium
# floors).
TEXT_ON_ROWS = [
    (token, surface, AA_TEXT, f"{why} on a {'zebra' if surface == 'row-zebra' else 'hovered'} row")
    for surface in ("row-zebra", "row-hover")
    for token, why in (("drill-text", ".drill link text"), ("text-muted", ".drill::after and .change-baseline"),
                       ("text-secondary", "secondary cell copy"), ("text-primary", "cell copy"),
                       ("status-good", ".change-added"), ("status-critical", ".change-removed"),
                       ("warn", "td.num.warn"))
]
# Active tab labels sit on the page; the accent also tints a card edge and the hero numeral.
# Derived from the stylesheet, not hardcoded: a hardcoded list silently stops covering a
# new tab, which is exactly what happened when `policy` and `nsaudit` were added — the
# suite stayed green while two accents went unchecked.
def _tab_tokens(css: str) -> list[str]:
    return sorted(set(re.findall(r"--(tab-[a-z]+):", css)))


TAB_NAMES = _tab_tokens(CSS.read_text())
TABS = [(token, "page", AA_TEXT, f"active {token} label") for token in TAB_NAMES]


@pytest.mark.parametrize("theme", VARIANTS)
@pytest.mark.parametrize(
    "token,background,required,why",
    TEXT_ON_PAGE + TEXT_ON_CARD + GRAPHICAL + TABS + WARN_TEXT + TEXT_ON_ROWS,
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


def test_visibility_labels_use_only_vetted_tokens():
    """The scope pill, banner and refusal ship NO colour of their own: every colour they
    use must be a var(--token) already covered by the contrast tables above, in both
    themes. A literal hex in that block would be the first colour on the page outside
    this file's checks — which is exactly how the nine original failures happened."""
    css = CSS.read_text()
    m = re.search(r"/\* ---- Visibility tier(.*?)\.runbook", css, re.S)
    assert m, "the visibility-tier style block is missing from app.css"
    block = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S)
    assert "#" not in block, "a literal colour crept into the visibility styles; use a token"
    for cls in (".scope-pill", ".scope-banner", ".scope-refusal"):
        assert cls in block, f"{cls} is not styled in the visibility block"


def _mix_srgb(foreground: str, background: str, weight: float) -> str:
    """color-mix(in srgb, fg <weight>, bg) for opaque colours, as the export note's background does."""
    ch = lambda h: [int(h.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{round(f * weight + b * (1 - weight)):02x}" for f, b in zip(ch(foreground), ch(background)))


@pytest.mark.parametrize("theme", VARIANTS)
@pytest.mark.parametrize("background", ["page", "page-2"])
def test_the_partial_export_edge_clears_graphical_contrast_on_the_page(themes, theme, background):
    """The export note's warning edge (`.export-note.partial`) sits on the page gradient, not on a
    card, and its background is the badge amber at 8% — so the edge token is measured against that
    tinted page, where the badge amber itself fell to 2.5:1 (review of C1, second pass, Codex)."""
    tokens = themes[theme]
    edge = tokens["status-warning-edge"]
    tinted = _mix_srgb(tokens["status-warning"], tokens[background], 0.08)
    got = ratio(edge, tinted)
    assert got >= AA_LARGE_OR_GRAPHIC, f"{theme}: {edge} on the tinted --{background} {tinted} is {got:.2f}:1"



@pytest.mark.parametrize("palette", PALETTES[1:])
def test_the_os_dark_palette_twins_match(palette):
    """A dark palette is written twice — once guarded by prefers-color-scheme for a reader who set
    nothing, once for an explicit data-theme="dark" — and the contrast checks read only the
    explicit one. If the two ever drift, the un-stamped reader gets colours nobody measured."""
    css = CSS.read_text()
    explicit = _block(css, rf':root\[data-theme="dark"\]\[data-palette="{palette}"\]\s*\{{(.*?)\n\}}')
    os_dark = _block(css, rf':root:where\(:not\(\[data-theme="light"\]\)\)\[data-palette="{palette}"\]\s*\{{(.*?)\n  \}}')
    assert explicit, f"no explicit dark block for {palette}"
    assert os_dark == explicit, f"{palette}: the OS-dark twin differs from the explicit dark block"


def test_a_palette_overrides_only_the_status_hues():
    """--accent and the --tab-* identities are the page's own colour, already separated on lightness
    for a deuteranope; a palette that repainted them would change which page you are on."""
    css = CSS.read_text()
    for palette in PALETTES[1:]:
        for theme in ("light", "dark"):
            names = set(_palette_block(css, theme, palette))
            assert names, f"{theme}/{palette} defines nothing"
            allowed = {"status-good", "status-warning", "status-warning-edge", "status-critical", "text-muted", "warn"}
            assert names <= allowed, f"{theme}/{palette} overrides {sorted(names - allowed)}"


HOME_HOVER_WASH = 0.06   # .home .hrow:hover — keep in step with the stylesheet


def _mix(fg: str, bg: str, pct: float) -> str:
    """`color-mix(in srgb, fg pct%, transparent)` painted over `bg` — what the eye actually gets."""
    f, b = fg.lstrip("#"), bg.lstrip("#")
    out = []
    for i in (0, 2, 4):
        out.append(round(int(f[i:i + 2], 16) * pct + int(b[i:i + 2], 16) * (1 - pct)))
    return "#" + "".join(f"{c:02x}" for c in out)


@pytest.mark.parametrize("variant", VARIANTS)
def test_home_text_clears_aa_on_the_surfaces_it_actually_sits_on(themes, variant):
    """#158's rows carry a hover wash, and a token measured on the card is not measured on the wash: with
    `--text-muted` (4.68:1 on the card in light) under a 10 % accent wash the row's meta read 4.05:1, and
    the amber pills on `--page-2` read 4.40:1 (review of #158, Codex; Grok measured the same shape). What
    is checked here is Home's own choice — which token goes on a washed row, and which surface a pill sits
    on. The tokens' own headroom on the shared surfaces is #184's, and this guard must not be read as
    covering it."""
    t = themes[variant]
    card = t["surface-1"]
    wash = _mix(t["tab-home"], card, HOME_HOVER_WASH)
    failures = []
    for label, fg, bg in (("row text on the card", t["text-secondary"], card),
                          ("row text on the hover wash", t["text-secondary"], wash),
                          ("the amber pill on its own surface", t["warn"], card)):
        r = ratio(fg, bg)
        if r < AA_TEXT:
            failures.append(f"{label}: {fg} on {bg} is {r:.2f}:1")
    assert not failures, f"{variant} — Home text under {AA_TEXT}:1:\n  " + "\n  ".join(failures)


def _hue(hex_colour: str) -> float:
    import colorsys
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hls(r, g, b)[0] * 360


# Warning text and critical text are read side by side (td.num.warn next to .change-removed on the Users
# tab); when a palette put both on the same hue they were told apart by weight alone. The bar is the
# Okabe-Ito reference's own separation between its two warm colours, vermilion (27°) and orange (41°):
# 14°. The light CVD palettes inherited the default amber and sat 0.5° from their vermilion critical
# (#204 review); each carries its own warning hue now.
@pytest.mark.parametrize("theme", VARIANTS)
def test_warning_text_keeps_its_own_hue_beside_critical(themes, theme):
    t = themes[theme]
    d = abs(_hue(t["warn"]) - _hue(t["status-critical"]))
    d = min(d, 360 - d)
    assert d >= 14, f"{theme}: --warn {t['warn']} and --status-critical {t['status-critical']} are {d:.1f}° apart"


# The KPI page's critical chip is text on a chip whose default background is the translucent --zebra,
# inside a row that may be hovered: zebra over the hover wash over the card is a fourth surface the row
# table does not model, and the text measured 4.06-4.31 there (#204 review). The chip paints an opaque
# token surface of its own, and the text is held to the bar on that surface.
@pytest.mark.parametrize("theme", VARIANTS)
def test_the_kpi_critical_chip_text_sits_on_an_opaque_vetted_surface(themes, theme):
    rule = re.search(r"\.kpi-page \.chip\.crit\s*\{([^}]*)\}", CSS.read_text(), re.S)
    assert rule, "the KPI critical-chip rule is missing"
    background = re.search(r"background:\s*var\(--([a-z0-9-]+)\)", rule.group(1))
    assert background, "the KPI critical chip needs its own opaque token background"
    t = themes[theme]
    got = ratio(t["status-critical"], t[background.group(1)])
    assert got >= AA_TEXT, f"{theme}: KPI critical chip text is {got:.2f}:1 on --{background.group(1)}"
