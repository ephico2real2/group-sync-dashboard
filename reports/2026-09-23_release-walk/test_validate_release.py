"""The release script's two checks whose verdict must not depend on what the page or the store happens to hold.

Review of #335 (OB1-lite, NA-1 and NA-2). Run from the repository root:

    E2E_WALK_DIR=local-development/e2e-walk local-development/.venv/bin/python -m pytest \\
        reports/2026-09-23_release-walk/test_validate_release.py -q -p no:cacheprovider

VR_PATH may point at another copy of validate_release.py; by default the sibling script is tested.
"""
from __future__ import annotations

import importlib.util
import os
import pathlib
import types

import pytest
from playwright.sync_api import sync_playwright

VR = pathlib.Path(os.environ.get("VR_PATH") or pathlib.Path(__file__).with_name("validate_release.py"))
spec = importlib.util.spec_from_file_location("validate_release", VR)
vr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vr)

LOGIN_AT = "2026-09-23T20:54:53Z"          # the walk's own clock, floored to the second (main())
CLUSTERS = [{"id": "dashboard"}]


def credential_row(at: str, observed_at: str, kind: str = "credential") -> dict:
    """A login_event row as /api/clusters/<id>/logins serves it (gsd/auditlog.py#event_dict)."""
    return {"user_name": "kubeadmin", "outcome": "success", "at": at, "provider": "developer",
            "detail": f"audit: {kind} allow via /login/developer", "pod_name": "crc", "observed_at": observed_at,
            "source": "audit-log", "audit_id": "x", "kind": kind, "client_id": None, "status_code": 302}


class FakeWalk:
    def __init__(self):
        self.page = types.SimpleNamespace(wait_for_timeout=lambda ms: None)
        self.recorded = []

    def record(self, step, ok, detail, screenshot=None, **extra):
        self.recorded.append((step, ok, detail))


def run_320(monkeypatch, rows: list[dict]) -> bool:
    def fake_api(w, path):
        if path == "/api/clusters":
            return {"status": 200, "json": CLUSTERS}
        return {"status": 200, "json": {"attempts": rows}}
    monkeypatch.setattr(vr, "api_json", fake_api)
    w = FakeWalk()
    vr.check_login_captured(w, LOGIN_AT, "kubeadmin", timeout_s=1)
    assert len(w.recorded) == 1 and w.recorded[0][0].startswith("#320")
    return w.recorded[0][1]


def test_320_a_backfilled_older_credential_row_is_not_this_runs_login(monkeypatch):
    """A form login from an earlier session, first observed by the poller after login_at (a backfill), is not
    the login this run made: its own instant is before login_at."""
    stale = credential_row(at="2026-09-23T16:53:42.465124Z", observed_at="2026-09-23T20:55:37Z")
    assert run_320(monkeypatch, [stale]) is False


def test_320_this_runs_form_login_is_found(monkeypatch):
    fresh = credential_row(at="2026-09-23T20:54:56.405173Z", observed_at="2026-09-23T20:55:37Z")
    assert run_320(monkeypatch, [fresh]) is True


def test_320_the_oauth_proxys_session_row_is_not_accepted(monkeypatch):
    session = credential_row(at="2026-09-23T20:54:56.420000Z", observed_at="2026-09-23T20:55:37Z", kind="session")
    assert run_320(monkeypatch, [session]) is False


# ---- #330 -----------------------------------------------------------------------------------------------------

HEAD = pathlib.Path(os.environ["E2E_WALK_DIR"]).resolve().parents[1]
CSS = (HEAD / "local-development/gsd/static/app.css").read_text()
ROWS = ["risk-row risk-high", "risk-row risk-high", "", "risk-row risk-high", "", "", "", "risk-row risk-high"]


def audit_page(wired: bool) -> str:
    """The audit page's three tables with Every grant collapsed (index.html#function nsAuditPage's shape);
    `wired` is whether its control opens it."""
    rows = "".join(f'<tr class="{c}"><td>u{i}</td><td>x</td></tr>' for i, c in enumerate(ROWS))
    js = """<script>document.querySelector('[data-ns-grants]').onclick = (e) => {
        document.getElementById('every-grant').removeAttribute('hidden');
        e.currentTarget.setAttribute('aria-expanded', 'true'); };</script>""" if wired else ""
    return f"""<!doctype html><html><head><style>{CSS}</style></head><body>
<section class="card"><table class="audit-table"><tbody><tr class="risk-row risk-high"><td>wide</td></tr></tbody></table></section>
<section class="card"><table class="audit-table"><tbody><tr class="risk-row risk-high"><td>a</td></tr>
<tr class="risk-row risk-medium"><td>b</td></tr><tr class="risk-row risk-high"><td>c</td></tr></tbody></table></section>
<section class="card"><div class="section-head"><h3 class="flush">Every grant</h3>
<button type="button" class="disclose" data-ns-grants aria-expanded="false" aria-controls="every-grant">
  <span class="disclose-arrow" aria-hidden="true">▸</span>
  Show 10 grants
</button></div>
<div id="every-grant" hidden><div class="scroll-x"><table class="audit-table"><tbody>{rows}</tbody></table></div></div>
</section>{js}</body></html>"""


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def test_330_a_section_that_never_opens_is_a_fail(browser):
    """The rows exist and compute a tint while hidden; a check that counts them without opening the section
    cannot tell what a reader sees."""
    page = browser.new_page()
    page.set_content(audit_page(wired=False))
    ok, detail = vr.check_even_row_tint(page)
    assert ok is False, detail
    assert "did not open" in detail
    page.close()


def test_330_an_open_section_counts_its_even_rows_per_tbody(browser):
    page = browser.new_page()
    page.set_content(audit_page(wired=True))
    ok, detail = vr.check_even_row_tint(page)
    assert ok is True, detail
    assert page.locator("#every-grant").get_attribute("hidden") is None
    assert "Every grant open" in detail
    assert "'table': 2, 'nth': 2" in detail and "'table': 2, 'nth': 4" in detail and "'table': 2, 'nth': 8" in detail
    page.close()
