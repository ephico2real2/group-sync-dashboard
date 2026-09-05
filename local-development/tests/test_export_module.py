"""The export module's switch: a config key, an env var, and the flag /api/version serves.

The export itself runs in the browser (tests/test_ui.py TestExport); this pins the one thing the
server contributes — the flag — in both states, and the parsing behind it.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.config import Settings, load_settings

BASE = """
clusters:
  - name: c1
    apiUrl: https://x
    tokenEnv: T
"""


def _client(tmp_path, **kw) -> TestClient:
    return TestClient(build_app(Settings(db_path=str(tmp_path / "t.db"), clusters=[], **kw),
                                run_poller=False))


def test_the_module_is_on_by_default_and_version_says_so(tmp_path):
    with _client(tmp_path) as c:
        assert c.get("/api/version").json()["features"]["export"] is True


def test_off_is_served_as_false_not_as_an_absent_key(tmp_path):
    """The page checks `=== true`; an absent key would also hide the control, but an explicit
    false is what lets an operator read the deployment's state off the endpoint."""
    with _client(tmp_path, ui_export_enabled=False) as c:
        assert c.get("/api/version").json()["features"]["export"] is False


def test_the_configmap_key_is_read(tmp_path, monkeypatch):
    monkeypatch.delenv("GSD_UI_EXPORT_ENABLED", raising=False)
    p = tmp_path / "c.yaml"
    p.write_text(BASE + "uiExportEnabled: false\n")
    assert load_settings(str(p)).ui_export_enabled is False
    p.write_text(BASE)
    assert load_settings(str(p)).ui_export_enabled is True


def test_the_env_var_wins_and_accepts_the_yaml_spellings(tmp_path, monkeypatch):
    p = tmp_path / "c.yaml"
    p.write_text(BASE + "uiExportEnabled: true\n")
    monkeypatch.setenv("GSD_UI_EXPORT_ENABLED", "off")
    assert load_settings(str(p)).ui_export_enabled is False
    monkeypatch.setenv("GSD_UI_EXPORT_ENABLED", "nonsense")
    assert load_settings(str(p)).ui_export_enabled is True, "the fallback is the default, on"
