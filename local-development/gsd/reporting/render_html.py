"""The HTML rendering of a Report: one self-contained document, escaped throughout."""

from __future__ import annotations

import html
from importlib import resources

from .model import KeyValues, Note, Report, Section, Table

_CSS = resources.files(__package__).joinpath("report.css").read_text(encoding="utf-8")


def _e(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _table(t: Table) -> str:
    if not t.rows:
        body = f'<p class="empty">{_e(t.empty_text)}</p>'
    else:
        head = "".join(f"<th>{_e(c)}</th>" for c in t.columns)
        rows = "".join("<tr>" + "".join(f"<td>{_e(v)}</td>" for v in r) + "</tr>" for r in t.rows)
        body = f"<table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>"
    note = f'<p class="note">{_e(t.note)}</p>' if t.note else ""
    return f'<div class="block"><h3>{_e(t.title)}</h3>{body}{note}</div>'


def _kv(k: KeyValues) -> str:
    rows = "".join(f"<tr><th>{_e(a)}</th><td>{_e(b)}</td></tr>" for a, b in k.items)
    return f'<div class="block"><h3>{_e(k.title)}</h3><table class="kv">{rows}</table></div>'


def _note(n: Note) -> str:
    return f'<p class="note {_e(n.level)}">{_e(n.text)}</p>'


def _section(s: Section) -> str:
    cls = ' class="break"' if s.page_break else ""
    blocks = "".join(_table(b) if isinstance(b, Table) else _kv(b) if isinstance(b, KeyValues) else _note(b) for b in s.blocks)
    return f"<section{cls}><h2>{_e(s.title)}</h2>{blocks}</section>"


def render_html(report: Report, product_title: str) -> str:
    """The whole document. The sha256 sits in the header AND the footer margin box so a printed
    page carries it whatever page the reader photographs."""
    marking = report.provenance.get("marking", "")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{_e(report.title)} — {_e(report.cluster)} — {_e(product_title)}</title>
<meta name="generator" content="{_e(product_title)} report service {_e(report.provenance.get('report_service_version'))}">
<meta name="gsd-sha256" content="{_e(report.sha256)}">
<style>{_CSS}
@page {{ @top-left {{ content: "{_e(marking)}"; }} @bottom-left {{ content: "sha256 {_e(report.sha256[:16])}… · run {_e(report.run_id)}"; }} }}
</style></head>
<body>
<header>
  <p class="marking">{_e(marking)}</p>
  <h1>{_e(report.title)}</h1>
  <p class="sub">{_e(product_title)} · cluster <strong>{_e(report.cluster)}</strong> · generated {_e(report.generated_at)} by {_e(report.generated_by)} ({_e(report.generated_by_note)})</p>
  <p class="sha">sha256 of the report data: <code>{_e(report.sha256)}</code></p>
  <button class="no-print" onclick="window.print()">Print / Save as PDF</button>
</header>
<main>{''.join(_section(s) for s in report.sections)}</main>
<footer><p>{_e(product_title)} — {_e(report.title)} — run {_e(report.run_id)} — this document is a rendering of the report data whose sha256 is printed above; the .json artefact of the same run carries the data.</p></footer>
</body></html>
"""
