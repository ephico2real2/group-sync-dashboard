"""The two renderings of one model (docs/specs/SPEC_C3_reporting_microservice.md §9.6): escaping, the inlined
stylesheet and the sha256 in the HTML; the lazy fpdf import; the PDF/A markers fpdf2 was measured to write.
The PDF tests need the vendored DejaVu faces: skipped with a reason where a checkout has not run
vendor-assets.sh, and FAILING under CI=true — the browser-test precedent for "must run in CI"."""
from __future__ import annotations

import ast
import hashlib
import os
import re
import sys
from pathlib import Path

import pytest

from gsd.reporting.model import Note, Report, Section, Table
from gsd.reporting.render_html import render_html

GSD = Path(__file__).resolve().parents[1] / "gsd"
VENDOR = GSD / "static" / "vendor"
REGULAR, BOLD = VENDOR / "DejaVuSans.ttf", VENDOR / "DejaVuSans-Bold.ttf"


def _report(group_name="team-a") -> Report:
    return Report(name="groups", title="Groups", cluster="crc", api_url="https://x", generated_at="2026-09-06T00:00:00Z",
                  generated_by="root", generated_by_note="proxy-verified", run_id="20260906T000000.000000Z-ab12",
                  params={}, coverage={}, provenance={"marking": "Handling: internal", "report_service_version": "0.18.0"},
                  totals={}, truncated=False, include_members=False,
                  sections=[Section("Inventory", [Table("Groups", ["group", "members"], [[group_name, 3]]), Note("a note", "caveat")])]).seal()


def _need_fonts():
    if REGULAR.is_file() and BOLD.is_file():
        return
    if os.environ.get("CI") == "true":
        pytest.fail("the DejaVu faces are missing under CI; run vendor-assets.sh --update and commit gsd/static/vendor")
    pytest.skip("gsd/static/vendor/DejaVuSans*.ttf absent — run ./vendor-assets.sh --update")


class TestHtml:
    def test_escapes_and_carries_the_sha_and_the_stylesheet(self):
        report = _report("<script>alert(1)</script>")
        html = render_html(report, "Group Sync Dashboard")
        assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
        assert f'name="gsd-sha256" content="{report.sha256}"' in html
        css = (GSD / "reporting" / "report.css").read_text()
        assert css.strip() in html, "the stylesheet is inlined: the artefact is self-contained"
        assert "Handling: internal" in html and "@page" in html

    def test_the_print_stylesheet_uses_only_the_three_greys(self):
        css = (GSD / "reporting" / "report.css").read_text()
        colours = {c.lower() for c in re.findall(r"#[0-9a-fA-F]{3,6}\b", css)}
        assert colours <= {"#000", "#fff", "#555"}, colours


class TestPdf:
    def test_fpdf_is_imported_lazily_and_the_package_imports_without_it(self):
        """The dashboard image ships gsd.reporting without the `report` extra: importing the package
        and the ticket module must not need fpdf. Checked in a SUBPROCESS with fpdf blocked — mutating
        sys.modules in this process left every other test holding stale module objects (a TicketError
        raised by a re-imported module is not the TicketError a test imported), which is how a first
        version of this test failed 33 unrelated tests under the full suite."""
        import subprocess, sys
        tree = ast.parse((GSD / "reporting" / "render_pdf.py").read_text())
        top = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
        assert all("fpdf" not in ast.dump(n) for n in top), "fpdf must be imported inside a function"
        probe = ("import sys; sys.modules['fpdf'] = None; sys.modules['fpdf.enums'] = None; sys.modules['fpdf.fonts'] = None; "
                 "import gsd.reporting, gsd.reporting.ticket, gsd.reporting.render_pdf; "
                 "from gsd.reporting.render_pdf import render_pdf; print('ok')")
        done = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, cwd=str(GSD.parent), timeout=60)
        assert done.returncode == 0 and done.stdout.strip() == "ok", done.stderr

    def test_the_vendored_faces_hash_to_the_lock(self):
        _need_fonts()
        lock = (VENDOR / "ASSETS.lock").read_text()
        for f in (REGULAR, BOLD):
            assert f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.name}" in lock, f.name

    def test_pdf_a_2b_carries_the_measured_markers(self):
        _need_fonts()
        from gsd.reporting.render_pdf import render_pdf
        out = render_pdf(_report(), "Group Sync Dashboard", "pdf/a-2b", str(REGULAR), str(BOLD))
        assert out.startswith(b"%PDF")
        assert b"/FontFile2" in out and b"/OutputIntent" in out
        assert b"<pdfaid:part>2</pdfaid:part>" in out and b"<pdfaid:conformance>B</pdfaid:conformance>" in out

    def test_a_plain_pdf_has_no_pdfa_id_and_3b_embeds_the_canonical_json(self):
        _need_fonts()
        from gsd.reporting.render_pdf import render_pdf
        plain = render_pdf(_report(), "T", "", str(REGULAR), str(BOLD))
        assert plain.startswith(b"%PDF") and b"pdfaid" not in plain
        canonical = _report().to_json().encode()
        three_b = render_pdf(_report(), "T", "pdf/a-3b", str(REGULAR), str(BOLD), canonical)
        assert b"/EmbeddedFile" in three_b
        two_b = render_pdf(_report(), "T", "pdf/a-2b", str(REGULAR), str(BOLD), canonical)
        assert b"/EmbeddedFile" not in two_b, "2b forbids attachments; the renderer embeds only under 3b/3u"

    def test_an_unknown_variant_is_refused(self):
        from gsd.reporting.render_pdf import render_pdf
        with pytest.raises(ValueError):
            render_pdf(_report(), "T", "pdf/x-1a", str(REGULAR), str(BOLD))
