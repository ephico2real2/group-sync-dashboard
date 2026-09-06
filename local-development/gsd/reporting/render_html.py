"""The HTML rendering of a Report: one self-contained document, from Jinja2 partials in an IMMUTABLE
sandbox (docs/specs/SPEC_C3_reporting_microservice.md, the dynamic-templates note).

WHY A SANDBOX FOR OUR OWN TEMPLATES. The templates ship in the wheel today, and the note keeps the door
open for operator-supplied partials later; the environment is built as if every template were untrusted,
so that later step changes a loader, not the trust model. Measured while the note was written: the plain
SandboxedEnvironment let a template call `report.provenance.update({...})` on the supplied dictionary, and a
default Environment reaches `os.environ` and the token both pods mount. So: ImmutableSandboxedEnvironment,
globals cleared, the `safe` filter removed, autoescape on, StrictUndefined, no reload — and a DETACHED
context of dicts, lists and scalars (`json.loads(report.to_json())`), never the live Report, settings or
paths. Every template is parsed at import and refused if it uses `|safe`, `Markup` or `{% autoescape
false %}`. The one value that is not escaped is the package's own stylesheet, which the RENDERER marks
safe — a template cannot.

The marking and the page furniture land inside <style>, where HTML escaping is the wrong escaping: a
marking that began with a newline closed the CSS string and the rule (measured; CSS Values §3.3). They go
through `css_string`, which encodes every code point as a six-digit CSS escape.
"""

from __future__ import annotations

import json
import re
from importlib import resources

from jinja2 import PackageLoader, StrictUndefined
from jinja2.sandbox import ImmutableSandboxedEnvironment
from markupsafe import Markup

from .model import Report

#: The partials the base layout resolves for any report, plus one per block kind the model names.
#: tests/test_reporting_render.py holds the EXACT set resolved for a synthetic report to this.
TEMPLATES = ("base.html", "furniture.css", "marking.html", "section.html", "block_table.html", "block_kv.html", "block_note.html")
#: Constructs no template may use: each defeats autoescaping.
FORBIDDEN = (re.compile(r"\|\s*safe\b"), re.compile(r"\bMarkup\b"), re.compile(r"\{%-?\s*autoescape\s+false"))

_CSS = resources.files(__package__).joinpath("report.css").read_text(encoding="utf-8")


class TemplateRefused(ValueError):
    """A template uses a construct that would bypass escaping."""


def css_string(value) -> str:
    """Every code point as a six-digit CSS escape, so no character can end the string or the rule."""
    return "".join(f"\\{ord(ch):06x}" for ch in ("" if value is None else str(value)))


def check_template_source(name: str, source: str) -> None:
    for pattern in FORBIDDEN:
        if pattern.search(source):
            raise TemplateRefused(f"template {name} uses {pattern.pattern!r}, which bypasses escaping")


def build_environment(loader=None) -> ImmutableSandboxedEnvironment:
    env = ImmutableSandboxedEnvironment(loader=loader or PackageLoader("gsd.reporting", "templates"),
                                        autoescape=True, undefined=StrictUndefined, auto_reload=False)
    env.globals.clear()
    env.filters.pop("safe", None)
    env.filters["css_string"] = css_string
    for name in TEMPLATES:
        source, _, _ = env.loader.get_source(env, name)
        check_template_source(name, source)
    return env


_ENV = build_environment()


def context(report: Report, product_title: str) -> dict:
    """The detached context: the report's own JSON round-tripped (dicts, lists, scalars — nothing with a
    method worth calling), the product title, the marking, the page furniture, and the stylesheet."""
    data = json.loads(report.to_json())
    return {
        "report": data,
        "product_title": product_title,
        "marking": (data.get("provenance") or {}).get("marking", ""),
        "furniture": f"sha256 {report.sha256[:16]}… · run {report.run_id}",
        "css": Markup(_CSS),
    }


def render_html(report: Report, product_title: str, env: ImmutableSandboxedEnvironment | None = None) -> str:
    """The whole document. The sha256 sits in the header AND the footer margin box so a printed page
    carries it whatever page the reader photographs."""
    return (env or _ENV).get_template("base.html").render(**context(report, product_title))
