"""The dashboard is named in ONE place, and every surface that shows the name reads it.

The header used to be a literal in five files. The last rename (8fc97a8) changed one of them,
and the signed-out page, the README and a spec anchor were caught up by hand over later commits
— which is how a product ends up with two names. Now `gsd.TITLE` is the name, the two HTML
files carry a placeholder the handlers fill, the API docs read the same constant, and this
file holds the README to it, because a README cannot read a Python constant on its own.
"""

from __future__ import annotations

import pathlib

from fastapi.testclient import TestClient

import gsd.api
from gsd import TITLE
from gsd.api import build_app
from gsd.config import Settings

HERE = pathlib.Path(__file__).resolve()
STATIC = HERE.parents[1] / "gsd" / "static"
README = HERE.parents[2] / "README.md"
PLACEHOLDER = "__GSD_TITLE__"


def _client(tmp_path) -> TestClient:
    return TestClient(
        build_app(Settings(db_path=str(tmp_path / "t.db"), clusters=[]), run_poller=False)
    )


def test_the_default_name_is_the_one_the_operator_chose():
    assert TITLE == "OCP Access Tracking Dashboard"


def test_the_page_carries_the_name_in_the_tab_title_and_the_header(tmp_path):
    body = _client(tmp_path).get("/").text
    assert f"<title>{TITLE}</title>" in body
    assert f"<h1>{TITLE}<span id=\"scope-note\">" in body
    assert PLACEHOLDER not in body, "a placeholder reached the browser"


def test_the_signed_out_page_carries_the_same_name(tmp_path):
    body = _client(tmp_path).get("/signed-out").text
    assert f"<title>Signed out — {TITLE}</title>" in body
    assert PLACEHOLDER not in body


def test_the_pages_stay_no_cache(tmp_path):
    """The substitution must not lose the header that makes a redeploy visible."""
    c = _client(tmp_path)
    for path in ("/", "/signed-out"):
        assert c.get(path).headers["cache-control"] == "no-cache, must-revalidate", path


def test_the_api_docs_read_the_same_constant(tmp_path):
    assert _client(tmp_path).get("/api/openapi.json").json()["info"]["title"] == TITLE


def test_the_name_is_text_not_markup(tmp_path, monkeypatch):
    """A name with an angle bracket must render as characters, never as an element."""
    monkeypatch.setattr(gsd.api, "TITLE", "A <b>bold</b> & odd name")
    body = _client(tmp_path).get("/").text
    assert "A &lt;b&gt;bold&lt;/b&gt; &amp; odd name" in body
    assert "<b>bold</b>" not in body


def test_the_static_files_carry_the_placeholder_and_not_a_literal():
    """The guard against the name being hard-coded back into a file."""
    for name in ("index.html", "signed-out.html"):
        text = (STATIC / name).read_text(encoding="utf-8")
        assert PLACEHOLDER in text, f"{name} lost its placeholder"
        assert TITLE not in text, f"{name} carries the name as a literal again"
        assert "Access Control Dashboard" not in text, f"{name} still carries the old name"


def test_the_readme_heading_is_the_name():
    """A README cannot import a constant, so the test is what holds it to the code."""
    first = README.read_text(encoding="utf-8").splitlines()[0]
    assert first == f"# {TITLE}", first


def test_the_old_name_is_gone_from_the_shipped_code():
    root = HERE.parents[1] / "gsd"
    hits = [p for p in root.rglob("*") if p.is_file() and p.suffix in {".py", ".html", ".css", ".js"}
            and "Access Control Dashboard" in p.read_text(encoding="utf-8", errors="ignore")]
    assert not hits, [str(p) for p in hits]
