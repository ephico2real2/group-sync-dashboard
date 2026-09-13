"""The PDF rendering of a Report with fpdf2 — the same model the HTML renders, so the hash on
page one is the hash of the same data.

fpdf2 is imported HERE and only here, lazily: the dashboard image ships this package without the
`report` extra and must import gsd.reporting.ticket without it (tests/test_reporting_render.py holds
the module-level import list to that).

PDF/A, measured on fpdf2 2.8.8 (docs/specs/SPEC_C3_reporting_microservice.md §6.2): base fonts are refused
under every PDF/A profile, so both faces of the vendored DejaVu Sans are registered; the table
heading row uses the bold face, which is why the bold file is not optional. Under 3b/3u the canonical
.json is embedded as an attachment — the one thing 3b exists for.
"""

from __future__ import annotations

from .model import KeyValues, Note, Report, Section, Table

#: Chart value / env spelling -> fpdf2 DocumentCompliance member. "" is a plain PDF.
_VARIANTS = {"pdf/a-1b": "PDFA_1B", "pdf/a-2b": "PDFA_2B", "pdf/a-2u": "PDFA_2U",
             "pdf/a-3b": "PDFA_3B", "pdf/a-3u": "PDFA_3U", "pdf/a-4": "PDFA_4"}
_FONT = "Body"
_MONO_FALLBACK = _FONT   # one face family; monospace is a screen nicety the PDF does without
#: The longest text one table cell draws, AFTER its whitespace is collapsed. fpdf2 refuses a row
#: taller than a page ("cannot be rendered on a single page"), which turned one 10,000-character
#: value into a failed run (review of C3, Codex) — and a character cap alone left 600 newlines a
#: 600-line row, still taller than a page (second pass, Cursor; measured). A report cell holds names
#: and labels, so runs of whitespace become one space and the cell wraps as one run of text; the
#: HTML and the JSON carry the whole value, the PDF says it was cut. THE BOUND IS THE NARROWEST
#: COLUMN, not the page: measured with the widest glyph, `W`×600 renders in a two-column table and
#: fails in the catalogue's six-column groups table; at nine columns (the widest table, "Group
#: bindings") ×400 fails and ×300 renders, at ten columns the same. 240 leaves a margin for a
#: wider table and a wider glyph.
CELL_MAX_CHARS = 240


def _cell_text(value) -> str:
    text = " ".join(("" if value is None else str(value)).split())
    return text if len(text) <= CELL_MAX_CHARS else text[:CELL_MAX_CHARS - 1] + "…"


def _pdf_class(variant: str):
    from fpdf import FPDF                      # noqa: WPS433 — lazy, see the module docstring
    from fpdf.enums import DocumentCompliance

    class ReportPDF(FPDF):
        product_title = ""
        marking = ""
        run_id = ""
        sha = ""

        def header(self):
            self.set_font(_FONT, "", 8)
            self.set_text_color(85)
            self.cell(0, 5, self.marking, align="L")
            self.cell(0, 5, self.product_title, align="R", new_x="LMARGIN", new_y="NEXT")
            self.set_text_color(0)
            self.ln(2)

        def footer(self):
            self.set_y(-14)
            self.set_font(_FONT, "", 8)
            self.set_text_color(85)
            self.cell(0, 5, f"sha256 {self.sha[:16]}… · run {self.run_id}", align="L")
            self.cell(0, 5, f"Page {self.page_no()} of {{nb}}", align="R")
            self.set_text_color(0)

    compliance = getattr(DocumentCompliance, _VARIANTS[variant]) if variant else None
    return ReportPDF, compliance


def render_pdf(report: Report, product_title: str, variant: str, font_regular: str, font_bold: str,
               canonical_json: bytes | None = None) -> bytes:
    """Bytes of the PDF. `variant` is "" or a key of _VARIANTS; `canonical_json` is embedded under
    3b/3u only (attachments are what those profiles permit and 2b forbids)."""
    if variant not in ("", *_VARIANTS):
        raise ValueError(f"unknown PDF variant {variant!r}")
    cls, compliance = _pdf_class(variant)
    pdf = cls(orientation="P", unit="mm", format="A4", enforce_compliance=compliance) if compliance else cls(orientation="P", unit="mm", format="A4")
    pdf.product_title, pdf.marking = product_title, report.provenance.get("marking", "")
    pdf.run_id, pdf.sha = report.run_id, report.sha256
    pdf.add_font(_FONT, "", font_regular)
    pdf.add_font(_FONT, "B", font_bold)
    pdf.set_title(f"{report.title} — {report.cluster}")
    pdf.set_author(product_title)
    pdf.set_creator(f"{product_title} report service {report.provenance.get('report_service_version', '')}")
    pdf.set_subject(f"run {report.run_id}; sha256 {report.sha256}")
    pdf.set_lang("en-US")
    pdf.set_margins(18, 18, 18)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_font(_FONT, "B", 18)
    pdf.multi_cell(0, 9, report.title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(_FONT, "", 9)
    pdf.set_text_color(85)
    pdf.multi_cell(0, 5, f"cluster {report.cluster} · generated {report.generated_at} by {report.generated_by} ({report.generated_by_note})", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(0, 5, f"sha256 of the report data: {report.sha256}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0)
    pdf.ln(3)
    for i, section in enumerate(report.sections):
        if section.page_break and i > 0:
            pdf.add_page()
        _section(pdf, section)
    if compliance is not None and variant in ("pdf/a-3b", "pdf/a-3u") and canonical_json is not None:
        pdf.embed_file(bytes=canonical_json, basename="report.json", desc="canonical report data (sha256 in the document subject)")
    return bytes(pdf.output())


def _section(pdf, section: Section) -> None:
    pdf.set_font(_FONT, "B", 13)
    pdf.multi_cell(0, 7, section.title, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    for block in section.blocks:
        if isinstance(block, Table):
            _table(pdf, block)
        elif isinstance(block, KeyValues):
            _kv(pdf, block)
        elif isinstance(block, Note):
            _note(pdf, block)


def _table(pdf, t: Table) -> None:
    pdf.set_font(_FONT, "B", 10)
    pdf.multi_cell(0, 6, t.title, new_x="LMARGIN", new_y="NEXT")
    if not t.rows:
        pdf.set_font(_FONT, "", 9)
        pdf.set_text_color(85)
        pdf.multi_cell(0, 5, t.empty_text, new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0)
    else:
        pdf.set_font(_FONT, "", 8)
        # fpdf2's table(): the heading row is bold (the registered B face — fpdf2 2.8.8 REQUIRES a
        # headings_style when the first row is a heading; `None` is refused with "headings_style must
        # be provided"), repeats on every page, and a row never splits across pages — the same rules
        # the CSS gives the HTML.
        from fpdf.fonts import FontFace                # lazy, like every fpdf import in this module
        with pdf.table(headings_style=FontFace(emphasis="BOLD"), line_height=4.2, padding=(0.6, 1.2), repeat_headings=1) as table:
            head = table.row()
            for c in t.columns:
                head.cell(str(c))
            for r in t.rows:
                row = table.row()
                for v in r:
                    row.cell(_cell_text(v))
    if t.note:
        _note(pdf, Note(t.note))
    pdf.ln(2)


def _kv(pdf, k: KeyValues) -> None:
    pdf.set_font(_FONT, "B", 10)
    pdf.multi_cell(0, 6, k.title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(_FONT, "", 8.5)
    with pdf.table(first_row_as_headings=False, col_widths=(34, 66), line_height=4.4, padding=(0.6, 1.2)) as table:
        for a, b in k.items:
            row = table.row()
            row.cell(_cell_text(a))
            row.cell(_cell_text(b))
    pdf.ln(2)


def _note(pdf, n: Note) -> None:
    pdf.set_font(_FONT, "B" if n.level == "warning" else "", 8.5)
    pdf.set_text_color(0 if n.level in ("warning", "caveat") else 85)
    pdf.multi_cell(0, 4.6, n.text, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0)
    pdf.ln(1)
