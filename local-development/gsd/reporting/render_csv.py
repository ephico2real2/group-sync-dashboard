"""The CSV rendering of a Report (#106, docs/specs/SPEC_F2_csv_format.md): one file per run, every block
of every section in order, each under a labelled record, so a spreadsheet opens the report's tables and a
script can split them.

WHY NOT csv.writer. The page's table export (index.html `csvField`, SPEC_C1) already decides how a cell
becomes CSV: RFC 4180 quoting, a formula guard, `true`/`false`, arrays joined with "; ". csv.writer writes
`True`, a list's Python repr, `""` for a lone empty field and no guard (SPEC_F2 §2.2), so one cell would be
two different texts in the two exports. `csv_field` is the browser's function, ported; a test pins the port
to the JavaScript source and runs both side by side where node is installed.

The renderer reads the report's own JSON (`json.loads(report.to_json())`), as the HTML renderer does: the
JSON types the page's export reads too. It prints the sha256 and never computes it, so a CSV cannot change
the seal.
"""

from __future__ import annotations

import json
import math
import re
from decimal import Decimal

from .model import Report

#: UTF-8's byte-order mark, first in the file: a spreadsheet opened by a double-click reads BOM-less UTF-8
#: in the local code page and mangles a non-ASCII name (index.html `CSV_BOM`, SPEC_C1).
CSV_BOM = "﻿"
#: index.html `csvField`'s formula initiators, tested after any leading whitespace: OWASP's = + - @ tab CR,
#: plus LF and the full-width = + - @ (U+FF1D, U+FF0B, U+FF0D, U+FF20).
_FORMULA = re.compile("^[\t\r\n ]*[=+\\-@\t\r\n＝＋－＠]")
#: RFC 4180 §2.6: a field holding a double quote, a comma or a line break is enclosed in double quotes.
_NEEDS_QUOTES = re.compile('[",\r\n]')
#: The label record that opens a table-like block. A kind not here and not a note is refused, so a new
#: block kind gets its CSV form on purpose, as it gets its HTML partial and its PDF routine.
_LABEL = {"table": "Table", "kv": "List"}


def _js_string(value) -> str:
    """JavaScript's String(value) for the JSON scalars a report cell holds. An int is written whole: past
    2**53 the page's JSON.parse has already rounded it, and the CSV keeps the value the .json holds."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return _js_number(value)
    return str(value)


def _js_number(value: float) -> str:
    """ECMAScript's Number::toString of a float. repr() picks the same shortest round-trip digits; only the
    layout differs: JavaScript writes 2 for 2.0, 0.00001 for 1e-05, 1e-7 for 1e-07, and 1e+21 where
    str(int(1e21)) wrote all 22 digits (ECMA-262 Number::toString: exponent form below 1e-6 and from 1e21)."""
    if not math.isfinite(value):
        return "NaN" if math.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
    if value == 0:
        return "0"
    sign, digits, exponent = Decimal(repr(value)).normalize().as_tuple()
    s, k = "".join(map(str, digits)), len(digits)
    n = exponent + k                                   # value = 0.<s> x 10**n, ECMA-262's n and k
    if k <= n <= 21:
        body = s + "0" * (n - k)
    elif 0 < n <= 21:
        body = s[:n] + "." + s[n:]
    elif -6 < n <= 0:
        body = "0." + "0" * -n + s
    else:
        body = s[0] + ("." + s[1:] if k > 1 else "") + ("e+" if n > 0 else "e-") + str(abs(n - 1))
    return ("-" if sign else "") + body


def csv_field(value) -> str:
    """One cell, written as index.html's `csvField` writes it: null is empty, a list joins with "; ",
    numbers and booleans are written as they are, a text a spreadsheet would evaluate gets a leading
    apostrophe, and a text holding a quote, a comma or a line break is quoted with its quotes doubled."""
    if value is None:
        return ""
    if isinstance(value, list):
        value = "; ".join(_js_string(v) for v in value)
    elif isinstance(value, (bool, int, float)):
        return _js_string(value)
    text = str(value)
    if _FORMULA.match(text):
        text = "'" + text
    if _NEEDS_QUOTES.search(text):
        text = '"' + text.replace('"', '""') + '"'
    return text


def _block(block: dict) -> list[list]:
    """A blank record, the block's label record, then its records. Generic over the three kinds."""
    kind = block["kind"]
    if kind == "note":
        return [[], [block["level"].capitalize(), block["text"]]]
    if kind not in _LABEL:
        raise ValueError(f"no CSV rendering for block kind {kind!r}")
    records = [[], [_LABEL[kind], block["title"]]]
    if kind == "kv":
        return records + [list(item) for item in block["items"]]
    # The columns say what was looked for even when nothing was found, so they head an empty table too.
    records += [block["columns"], *(block["rows"] or [[block["empty_text"]]])]
    if block.get("note"):
        records.append(["Note", block["note"]])
    return records


def render_csv(report: Report) -> str:
    """The whole file: the BOM, then CRLF-ended records (RFC 4180 §2.1). First the title and the sha256
    the run sealed, as the PDF prints them; then every section in order, page one included, each opened
    by a `Section` record that says whether the sha256 covers it."""
    doc = json.loads(report.to_json())
    records: list[list] = [["Report", doc["title"]], ["sha256 of the report data", doc["sha256"]]]
    for section in doc["sections"]:
        records += [[], ["Section", section["title"], "sealed" if section["sealed"] else "not sealed: states the run"]]
        for block in section["blocks"]:
            records += _block(block)
    return CSV_BOM + "\r\n".join(",".join(csv_field(v) for v in record) for record in records) + "\r\n"
