"""P2 — the report service's selector-labels env parsing and the trigger's --params-json transport
(docs/DESIGN_reporting_selectors_snapshots_and_windows.md §3)."""
from __future__ import annotations

import pytest

from gsd.reporting.config import ReportConfigError, _selector_labels_env
from gsd.reporting import trigger


class TestSelectorLabelsEnv:
    def test_json_list(self, monkeypatch):
        monkeypatch.setenv("GSD_REPORT_NS_SELECTOR_LABELS",
                           '["company.net/mnemonic","company.net/app-environment"]')
        assert _selector_labels_env() == ("company.net/mnemonic", "company.net/app-environment")

    def test_unset_falls_back_to_the_singular(self, monkeypatch):
        monkeypatch.delenv("GSD_REPORT_NS_SELECTOR_LABELS", raising=False)
        monkeypatch.setenv("GSD_REPORT_NS_SELECTOR_LABEL", "company.net/mnemonic")
        assert _selector_labels_env() == ("company.net/mnemonic",)

    def test_empty_json_array_falls_back_to_the_singular(self, monkeypatch):
        monkeypatch.setenv("GSD_REPORT_NS_SELECTOR_LABELS", "[]")
        monkeypatch.setenv("GSD_REPORT_NS_SELECTOR_LABEL", "company.net/mnemonic")
        assert _selector_labels_env() == ("company.net/mnemonic",)

    def test_neither_is_empty(self, monkeypatch):
        monkeypatch.delenv("GSD_REPORT_NS_SELECTOR_LABELS", raising=False)
        monkeypatch.delenv("GSD_REPORT_NS_SELECTOR_LABEL", raising=False)
        assert _selector_labels_env() == ()

    def test_duplicate_label_fails(self, monkeypatch):
        monkeypatch.setenv("GSD_REPORT_NS_SELECTOR_LABELS", '["a","a"]')
        with pytest.raises(ReportConfigError, match="duplicate"):
            _selector_labels_env()

    def test_malformed_json_fails(self, monkeypatch):
        monkeypatch.setenv("GSD_REPORT_NS_SELECTOR_LABELS", "not json")
        with pytest.raises(ReportConfigError, match="not a JSON array"):
            _selector_labels_env()

    def test_non_string_entries_fail(self, monkeypatch):
        monkeypatch.setenv("GSD_REPORT_NS_SELECTOR_LABELS", "[1, 2]")
        with pytest.raises(ReportConfigError, match="array of strings"):
            _selector_labels_env()


class _FakeResp:
    def __init__(self, status=202, body=None):
        self.status_code = status
        self.text = ""
        self._body = body or {"id": "r1", "status": "done"}

    def json(self):
        return self._body


class _FakeClient:
    """Records the POSTed run body; a --params-json test must not hit the network."""
    captured: dict = {}

    def __init__(self, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, path, json=None):
        _FakeClient.captured = {"path": path, "json": json}
        return _FakeResp()


class TestTriggerParamsJson:
    def _run(self, monkeypatch, tmp_path, extra):
        tok = tmp_path / "token"
        tok.write_text("secret")
        monkeypatch.setattr(trigger.httpx, "Client", _FakeClient)
        return trigger.main(["--url", "https://x", "--report", "namespace-access",
                             "--cluster", "crc-local", "--schedule", "weekly",
                             "--token-file", str(tok)] + extra)

    def test_params_json_becomes_the_run_params(self, monkeypatch, tmp_path):
        rc = self._run(monkeypatch, tmp_path,
                       ["--params-json", '{"selectors": {"company.net/mnemonic": ["demo"]}}'])
        assert rc == 0
        body = _FakeClient.captured["json"]
        assert body["params"] == {"selectors": {"company.net/mnemonic": ["demo"]}}
        assert body["report"] == "namespace-access" and body["schedule"] == "weekly"

    def test_param_scalars_merge_over_params_json(self, monkeypatch, tmp_path):
        rc = self._run(monkeypatch, tmp_path,
                       ["--params-json", '{"include_members": false}', "--param", "include_members=true"])
        assert rc == 0
        assert _FakeClient.captured["json"]["params"] == {"include_members": "true"}

    def test_malformed_params_json_exits_1_without_posting(self, monkeypatch, tmp_path):
        _FakeClient.captured = {}
        rc = self._run(monkeypatch, tmp_path, ["--params-json", "not json"])
        assert rc == 1
        assert _FakeClient.captured == {}   # never POSTed

    def test_non_object_params_json_exits_1(self, monkeypatch, tmp_path):
        rc = self._run(monkeypatch, tmp_path, ["--params-json", "[1,2]"])
        assert rc == 1
