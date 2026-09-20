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

    def test_unset_is_empty_and_the_removed_singular_is_ignored(self, monkeypatch):
        # The deprecated GSD_REPORT_NS_SELECTOR_LABEL is gone; only LABELS is read.
        monkeypatch.delenv("GSD_REPORT_NS_SELECTOR_LABELS", raising=False)
        monkeypatch.setenv("GSD_REPORT_NS_SELECTOR_LABEL", "company.net/mnemonic")
        assert _selector_labels_env() == ()

    def test_empty_json_array_is_empty(self, monkeypatch):
        monkeypatch.setenv("GSD_REPORT_NS_SELECTOR_LABELS", "[]")
        monkeypatch.setenv("GSD_REPORT_NS_SELECTOR_LABEL", "company.net/mnemonic")
        assert _selector_labels_env() == ()

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

    def test_blank_entry_fails_instead_of_being_silently_dropped(self, monkeypatch):
        # Only a literal [] defers to the singular; a blank entry is a config error (review #129, both).
        monkeypatch.setenv("GSD_REPORT_NS_SELECTOR_LABELS", '["company.net/mnemonic", " "]')
        with pytest.raises(ReportConfigError, match="non-empty strings"):
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


class TestTriggerClusterAgnosticAndFormats:
    """#149 R1/R3: the trigger names no cluster and no formats unless the schedule pins them, and a
    fan-out answer (`runs`) is waited for whole — the Job fails if ANY cluster's run failed."""

    def _tok(self, tmp_path):
        tok = tmp_path / "token"; tok.write_text("secret"); return str(tok)

    def test_no_cluster_and_no_formats_are_sent_unless_given(self, monkeypatch, tmp_path):
        monkeypatch.setattr(trigger.httpx, "Client", _FakeClient)
        rc = trigger.main(["--url", "https://x", "--report", "groups", "--schedule", "weekly", "--token-file", self._tok(tmp_path)])
        assert rc == 0
        body = _FakeClient.captured["json"]
        assert "cluster" not in body and "formats" not in body, body
        rc = trigger.main(["--url", "https://x", "--report", "groups", "--schedule", "weekly", "--token-file", self._tok(tmp_path),
                           "--cluster", "prod-east", "--format", "pdf"])
        assert rc == 0 and _FakeClient.captured["json"]["cluster"] == "prod-east" and _FakeClient.captured["json"]["formats"] == ["pdf"]

    def test_a_fan_out_is_waited_for_whole_and_one_failure_fails_the_job(self, monkeypatch, tmp_path, capsys):
        class _Resp:
            status_code = 202
            def __init__(self, body): self._b = body
            def json(self): return self._b
        polls = {"a": ["running", "done"], "b": ["running", "running", "failed"]}
        class _Client:
            def __init__(self, **kw): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def post(self, path, json=None):
                return _Resp({"runs": [{"id": "a", "cluster": "crc-local"}, {"id": "b", "cluster": "prod-east"}]})
            def get(self, path):
                run_id = path.rsplit("/", 1)[1]
                status = polls[run_id].pop(0) if len(polls[run_id]) > 1 else polls[run_id][0]
                return _Resp({"id": run_id, "cluster": "x", "status": status, "error": "boom" if status == "failed" else None})
        monkeypatch.setattr(trigger.httpx, "Client", _Client)
        monkeypatch.setattr(trigger.time, "sleep", lambda s: None)
        rc = trigger.main(["--url", "https://x", "--report", "groups", "--schedule", "weekly", "--token-file", self._tok(tmp_path), "--wait"])
        assert rc == 1, "one cluster's run failed: the Job fails"
        out = capsys.readouterr().out
        assert '"clusters": ["crc-local", "prod-east"]' in out and '"status": "done"' in out and '"status": "failed"' in out


    def test_the_single_run_line_is_unchanged_and_an_empty_fan_out_fails(self, monkeypatch, tmp_path, capsys):
        # Review of PR #220 (Codex): the single-run path printed a list where it used to print the id;
        # and {"runs": []} exited 0 — a schedule that reached no cluster is not a run that happened.
        monkeypatch.setattr(trigger.httpx, "Client", _FakeClient)
        rc = trigger.main(["--url", "https://x", "--report", "groups", "--schedule", "weekly", "--token-file", self._tok(tmp_path)])
        assert rc == 0 and '"submitted": "r1"' in capsys.readouterr().out
        class _Empty(_FakeClient):
            def post(self, path, json=None): return _FakeResp(body={"runs": []})
        monkeypatch.setattr(trigger.httpx, "Client", _Empty)
        rc = trigger.main(["--url", "https://x", "--report", "groups", "--schedule", "weekly", "--token-file", self._tok(tmp_path)])
        assert rc == 1 and "queued no run" in capsys.readouterr().err


class _FakeResp409:
    status_code = 409
    text = "outside the reporting window"
    headers = {"Retry-After": "3600"}

    def json(self):
        return {}


class _FakeClient409(_FakeClient):
    def post(self, path, json=None):
        _FakeClient.captured = {"path": path, "json": json}
        return _FakeResp409()


class TestTriggerWindow:
    """The schedule Job maps the create_run 409 (window closed, design §5) to exit 0 — a SKIP, not a
    CronJob failure, so Kubernetes does not mark the Job failed or retry it into the window."""

    def test_409_outside_the_window_is_a_skip_exit_0(self, monkeypatch, tmp_path):
        tok = tmp_path / "token"
        tok.write_text("secret")
        monkeypatch.setattr(trigger.httpx, "Client", _FakeClient409)
        rc = trigger.main(["--url", "https://x", "--report", "namespace-access", "--cluster", "crc-local",
                           "--schedule", "weekly", "--token-file", str(tok)])
        assert rc == 0
