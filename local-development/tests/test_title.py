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


def test_a_reload_that_finds_the_same_page_costs_a_304(tmp_path):
    """no-cache means revalidate, and revalidation needs a validator (MDN's pattern for
    always-fresh HTML: no-cache + ETag + Last-Modified, answered with a bodiless 304). The
    FileResponse this replaced sent the validators but never answered a conditional request;
    the first substitution sent neither (review finding)."""
    c = _client(tmp_path)
    for path in ("/", "/signed-out"):
        first = c.get(path)
        etag = first.headers.get("etag")
        assert etag and etag.startswith('"'), (path, first.headers)
        assert first.headers.get("last-modified", "").endswith(" GMT"), path
        again = c.get(path, headers={"If-None-Match": etag})
        assert again.status_code == 304 and again.content == b"", path
        # RFC 9110 §15.4.5: the 304 SHOULD carry Cache-Control and ETag.
        assert again.headers["etag"] == etag
        assert again.headers["cache-control"] == "no-cache, must-revalidate"
        assert again.headers["last-modified"] == first.headers["last-modified"]


def test_if_none_match_is_compared_weakly_over_a_list(tmp_path):
    """RFC 9110 §13.1.2: weak comparison, and the field is a comma-separated list — a browser
    behind a proxy that weakened the tag must still get its 304."""
    c = _client(tmp_path)
    etag = c.get("/").headers["etag"]
    assert c.get("/", headers={"If-None-Match": f'"stale", W/{etag}'}).status_code == 304
    assert c.get("/", headers={"If-None-Match": "*"}).status_code == 304
    assert c.get("/", headers={"If-None-Match": '"stale"'}).status_code == 200


def test_if_modified_since_answers_when_there_is_no_etag_to_compare(tmp_path):
    c = _client(tmp_path)
    last = c.get("/").headers["last-modified"]
    assert c.get("/", headers={"If-Modified-Since": last}).status_code == 304
    assert c.get("/", headers={"If-Modified-Since": "Thu, 01 Jan 1970 00:00:00 GMT"}).status_code == 200
    assert c.get("/", headers={"If-Modified-Since": "not a date"}).status_code == 200


def test_the_etag_follows_the_name(tmp_path, monkeypatch):
    """A validator that survived a rename would serve the old header from the browser cache."""
    c = _client(tmp_path)
    before = c.get("/").headers["etag"]
    monkeypatch.setattr(gsd.api, "TITLE", "Another Name")
    after = c.get("/").headers["etag"]
    assert before != after
    assert c.get("/", headers={"If-None-Match": before}).status_code == 200


def test_the_raw_static_paths_serve_the_rendered_page_too(tmp_path):
    """The /static mount serves the source files, placeholder and all (review finding).
    The two routes registered ahead of it must shadow them with the rendered page."""
    c = _client(tmp_path)
    for path in ("/static/index.html", "/static/signed-out.html"):
        body = c.get(path).text
        assert PLACEHOLDER not in body, f"{path} leaked the placeholder"
        assert TITLE in body, path
    # And the mount itself still serves the real assets.
    assert c.get("/static/app.css").status_code == 200
    # Out of the schema, like the docs-UI routes: they are the page, not the API.
    assert not [p for p in c.get("/api/openapi.json").json()["paths"] if p.startswith("/static/")]


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


def test_the_old_names_are_gone_from_the_shipped_code():
    """Both of them: the pre-rename header and the generic name the API docs and the favicon
    label carried from before the first rename. `vendor/` is third-party and not ours to edit."""
    root = HERE.parents[1] / "gsd"
    hits = [
        (str(p), old)
        for p in root.rglob("*")
        if p.is_file() and p.suffix in {".py", ".html", ".css", ".js", ".svg"} and "vendor" not in p.parts
        for old in ("Access Control Dashboard", "GroupSync dashboard")
        if old in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert not hits, hits
