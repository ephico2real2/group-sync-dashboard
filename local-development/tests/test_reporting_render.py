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

from gsd.reporting.model import KeyValues, Note, Report, Section, Table
from gsd.reporting.render_html import render_html

GSD = Path(__file__).resolve().parents[1] / "gsd"
VENDOR = GSD / "static" / "vendor"
REGULAR, BOLD = VENDOR / "DejaVuSans.ttf", VENDOR / "DejaVuSans-Bold.ttf"


def _report(group_name="team-a") -> Report:
    return Report(name="groups", title="Groups", cluster="crc", api_url="https://x", generated_at="2026-09-06T00:00:00Z",
                  generated_by="root", generated_by_note="proxy-verified", run_id="20260906T000000.000000Z-ab12",
                  params={}, coverage={}, provenance={"marking": "Handling: internal", "report_service_version": "0.18.0"},
                  totals={}, truncated=False, include_members=False,
                  sections=[Section("Inventory", [Table("Groups", ["group", "members"], [[group_name, 3]]), KeyValues("Totals", [("groups", 1)]), Note("a note", "caveat")])]).seal()


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

    def test_exactly_the_shipped_partials_are_resolved_for_a_report_with_every_block_kind(self):
        """The dynamic-templates note (d): a RECORDING loader around the environment, asserting the
        exact set of templates a synthetic report resolves — not markers a template could omit."""
        from jinja2 import PackageLoader
        from gsd.reporting.render_html import TEMPLATES, build_environment
        seen: list[str] = []
        class Recording(PackageLoader):
            def get_source(self, environment, template):
                seen.append(template)
                return super().get_source(environment, template)
        env = build_environment(Recording("gsd.reporting", "templates"))
        seen.clear()
        render_html(_report(), "T", env=env)
        assert set(seen) == set(TEMPLATES), (sorted(set(seen)), sorted(TEMPLATES))

    def test_a_marking_with_a_newline_cannot_close_the_css_string(self):
        """Measured while the note was written: a marking beginning with a newline closed the CSS
        string and the @page rule. css_string encodes every code point as a six-digit escape."""
        from gsd.reporting.render_html import css_string
        report = _report()
        report.provenance["marking"] = "\nHandling: \"internal\"; } body { display: none } /*"
        html = render_html(report, "T")
        style = html[html.index("<style>"):html.index("</style>")]
        assert "\nHandling" not in style and "} body { display: none }" not in style
        assert css_string("\n") == "\\00000a" and css_string("a") == "\\000061"
        assert "\\00000a\\000048" in style       # the escaped newline then "H"

    @pytest.mark.parametrize("source", ['{{ x|safe }}', '{{ Markup(x) }}', '{% autoescape false %}{{ x }}{% endautoescape %}'])
    def test_the_three_escape_bypasses_are_refused_before_render(self, source):
        from jinja2 import DictLoader
        from gsd.reporting.render_html import TEMPLATES, TemplateRefused, build_environment
        shipped = {name: (GSD / "reporting" / "templates" / name).read_text() for name in TEMPLATES}
        with pytest.raises(TemplateRefused):
            build_environment(DictLoader({**shipped, "block_note.html": source}))

    def test_the_sandbox_refuses_environment_reads_callables_and_mutation(self):
        """The note's measurements, re-run: no globals, no callable on the context's values (the
        context is detached JSON, so there is nothing with a method worth calling), and the immutable
        sandbox refuses a mutation even on a dict."""
        from jinja2 import DictLoader, StrictUndefined
        from jinja2.exceptions import SecurityError, UndefinedError
        from gsd.reporting.render_html import TEMPLATES, build_environment, context
        shipped = {name: (GSD / "reporting" / "templates" / name).read_text() for name in TEMPLATES}
        ctx = context(_report(), "T")
        def render(src):
            env = build_environment(DictLoader({**shipped, "probe": src}))
            return env.get_template("probe").render(**ctx)
        for hostile in ("{{ cycler.__init__.__globals__.os.environ }}", "{{ self._TemplateReference__context.environment.loader }}",
                        "{{ report.canonical() }}", "{{ report.to_json() }}", "{{ report.provenance.update({'marking': 'x'}) }}",
                        "{{ report.__class__ }}", "{{ ''.__class__.__mro__ }}"):
            with pytest.raises((SecurityError, UndefinedError, TypeError, AttributeError)):
                render(hostile)
        assert render("{{ report.provenance.marking }}") == "Handling: internal"
        assert ctx["report"]["provenance"]["marking"] == "Handling: internal", "the supplied dict was not mutated"

    def test_the_catalogue_never_imports_a_renderer_or_markup(self):
        """The note's AST allow-list: catalogue modules return data, never markup — they may import the
        stdlib, gsd.state, gsd.reporting.config/model/snapshot and catalogue.common; never render_html,
        render_pdf, jinja2, fpdf, xml.etree or html."""
        forbidden = {"render_html", "render_pdf", "jinja2", "fpdf", "xml", "html", "markupsafe"}
        for path in sorted((GSD / "reporting" / "catalogue").glob("*.py")):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""] + [f"{node.module or ''}.{a.name}" for a in node.names]
                for n in names:
                    assert not ({p for p in n.split(".")} & forbidden), (path.name, n)


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

    def test_a_giant_cell_is_cut_in_the_pdf_and_whole_in_the_html(self):
        """Codex, review C3: fpdf2 refuses a row taller than a page, which failed the whole run on one
        10,000-character value. The PDF bounds a cell and marks the cut; the HTML carries it all."""
        _need_fonts()
        from gsd.reporting.render_pdf import CELL_MAX_CHARS, render_pdf
        report = _report("x" * 10_000)
        out = render_pdf(report, "T", "pdf/a-2b", str(REGULAR), str(BOLD))
        assert out.startswith(b"%PDF") and CELL_MAX_CHARS < 10_000
        assert "x" * 10_000 in render_html(report, "T")

    def test_an_unknown_variant_is_refused(self):
        from gsd.reporting.render_pdf import render_pdf
        with pytest.raises(ValueError):
            render_pdf(_report(), "T", "pdf/x-1a", str(REGULAR), str(BOLD))
