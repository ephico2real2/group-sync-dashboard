"""The lookup's (#174) shipped text says what the code does — three places that had drifted after the
review's passes rewrote the mechanism (review of #174, pass 3, OB3):

  * app.css's lookup block said the match was "marked in the accent's wash"; pass 1 dropped the wash
    (`mark { background: none; … font-weight: 700 }`) because it put the link text at 3.4:1.
  * index.html's header comment on `hl` said "longest term first … one pass"; pass 2 replaced that with
    ranges merged over every occurrence, and the comment INSIDE the function says so — the header did not.
  * the CHANGELOG's #174 entry recorded pass 1 and not pass 2 (the union, the walk step, #184's routing),
    where the #167 entry beside it carries every pass.

A guard over prose is narrow on purpose: it proves the text no longer claims a mechanism the code lost,
not that the prose is right — the same guarantee `test_docs_citations.py` gives for anchors."""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
CSS = (ROOT / "gsd" / "static" / "app.css").read_text(encoding="utf-8")
HTML = (ROOT / "gsd" / "static" / "index.html").read_text(encoding="utf-8")
CHANGELOG = (ROOT.parent / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")


def _lookup_css_block() -> str:
    start = CSS.index("---- The lookup (#174)")
    end = CSS.index("---- Utilities", start)
    return CSS[start:end]


def test_the_sheets_lookup_comment_does_not_promise_a_wash():
    block = _lookup_css_block()
    assert "mark { background: none;" in block, "the mark rule moved; update this guard's anchor"
    comment = re.sub(r"\s+", " ", block.split("mark {")[0])   # the comment wraps mid-phrase
    assert "accent's wash" not in comment, (
        "the block's comment still says the match is marked in the accent's wash; the rule says no fill")


def test_the_header_comment_on_hl_does_not_describe_the_pass_1_mechanism():
    start = HTML.index("const LOOKUP_PER_KIND")
    end = HTML.index("function hl(text, query)", start)
    header = HTML[start:end]
    assert "Longest term first" not in header and "one pass" not in header, header
    body_start = end
    body_end = HTML.index("\nfunction lookupMatches", body_start)
    assert "merged" in HTML[body_start:body_end], "the function's own comment should say the ranges are merged"


def test_the_changelog_records_every_pass_of_the_lookups_review():
    m = re.search(r"^- \*\*One lookup over the three kinds \(#174\)\.\*\*.*?(?=^- \*\*)", CHANGELOG, re.S | re.M)
    assert m, "the #174 entry is not in the CHANGELOG"
    entry = m.group(0)
    assert "Review, pass 1" in entry
    assert "Review, pass 2" in entry, "pass 2 (the union marking, the walk step, #184) is in the record but not the CHANGELOG"
