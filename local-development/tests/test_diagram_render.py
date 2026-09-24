"""docs/diagrams/render.py's exit status, on every path its docstring promises (SPEC_D2b §7).

The renderer's value is its refusals: a figure drawn in a fallback face, or a page that scrolls sideways at
375 px, looks like a design choice once it is a PNG. So every page it opens, the 375 px one included, must turn a
page error, a failed request or an HTTP error into a non-zero exit. Playwright is replaced by a stand-in that fires
those events on demand, so this needs no browser and no network; the real render is SPEC_D2b §7's "After the
blocks" step.
"""

from __future__ import annotations

import importlib.util
import pathlib
from types import SimpleNamespace

import pytest

RENDER = pathlib.Path(__file__).resolve().parents[2] / "docs" / "diagrams" / "render.py"

# case -> (fired on the 375 px page?, event, payload); "ok", "mismatch" and "scroll" fire nothing.
EVENTS = {
    "offline": (False, "requestfailed", SimpleNamespace(url="https://fonts.invalid/face.woff2")),
    "404": (False, "response", SimpleNamespace(url="https://fonts.invalid/face.woff2", status=404)),
    "pageerror": (False, "pageerror", RuntimeError("broken page")),
    "phone-requestfailed": (True, "requestfailed", SimpleNamespace(url="https://fonts.invalid/face.woff2")),
    "phone-404": (True, "response", SimpleNamespace(url="https://fonts.invalid/face.woff2", status=404)),
    "phone-pageerror": (True, "pageerror", RuntimeError("broken page")),
}


def _render():
    spec = importlib.util.spec_from_file_location("diagram_render", RENDER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("case", ["ok", "mismatch", "scroll", *EVENTS])
def test_every_page_turns_a_failure_into_a_non_zero_exit(monkeypatch, tmp_path, case):
    render = _render()

    class Page:
        def __init__(self, phone: bool):
            self.phone, self.handlers = phone, {}

        def on(self, name, callback):
            self.handlers.setdefault(name, []).append(callback)

        def goto(self, url, **kwargs):
            assert url.startswith("file:")
            on_phone, event, payload = EVENTS.get(case, (None, None, None))
            if on_phone is self.phone:
                for callback in self.handlers.get(event, []):
                    callback(payload)

        def evaluate(self, expression):
            return (500 if case == "scroll" else 375) if "scrollWidth" in expression else True

        def locator(self, selector):
            assert selector == ".fig-scroll"
            return self

        def count(self):
            return 3 if case == "mismatch" else 4

        def nth(self, index):
            return self

        def screenshot(self, path):
            pathlib.Path(path).write_bytes(b"png")

        def close(self):
            pass

    class Browser:
        def new_page(self, *, viewport, **kwargs):
            return Page(viewport["width"] == 375)

        def close(self):
            pass

    class Playwright:
        chromium = SimpleNamespace(launch=Browser)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(render, "sync_playwright", Playwright)
    page = tmp_path / "page.html"
    page.write_text("<html><body>four figures</body></html>")
    out = tmp_path / "png"
    monkeypatch.setattr(render.sys, "argv", ["render.py", str(page), str(out), "a,b,c,d"])
    assert render.main() == (0 if case == "ok" else 1), case
    if case == "ok":
        assert len(list(out.glob("*.png"))) == 8
