"""#109 (docs/specs/SPEC_F4_webhook_delivery.md): the schedule Job delivers each finished run to a webhook.

The trigger is driven end to end with real httpx clients over one MockTransport that plays both the report
service and the receiver, so a status code, a Retry-After header and a transport error behave as httpx makes
them behave. The webhook URL carries a marker that must never reach stdout or stderr.
"""

from __future__ import annotations

import ast
import base64
import json
from pathlib import Path

import httpx
import pytest

from gsd.reporting import trigger

SERVICE = "https://svc.test:8443"
SECRET_PART = "T0SECRET/B0SECRET/xoxSECRETPATH"
HOOK = f"https://hooks.receiver.test/services/{SECRET_PART}"
REPORTING = Path(__file__).resolve().parents[1] / "gsd" / "reporting"


class _Lab:
    """The report service (a fan-out of two runs) and the receiver, behind one transport."""

    def __init__(self, hook_answers=None, create_status=202, run_status=None, artifact_answers=None):
        self.hook_answers = list(hook_answers or [httpx.Response(200)])
        self.artifact_answers = list(artifact_answers or [
            httpx.Response(200, content=b"<html>report</html>",
                           headers={"content-type": "text/html; charset=utf-8"})])
        self.create_status = create_status
        self.run_status = run_status or {"r-crc": "done", "r-east": "done"}
        self.events: list[dict] = []
        self.hook_headers: list[httpx.Headers] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "hooks.receiver.test":
            self.hook_headers.append(request.headers)
            self.events.append(json.loads(request.content))
            answer = self.hook_answers.pop(0) if len(self.hook_answers) > 1 else self.hook_answers[0]
            if isinstance(answer, Exception):
                raise answer
            return answer
        assert "authorization" in request.headers, "the service is always called with the token"
        path = request.url.path
        if request.method == "POST" and path == "/report/api/runs":
            if self.create_status != 202:
                return httpx.Response(self.create_status, headers={"Retry-After": "3600"}, json={"detail": "closed"})
            return httpx.Response(202, json={"runs": [{"id": "r-crc", "cluster": "crc-local"},
                                                      {"id": "r-east", "cluster": "prod-east"}]})
        if path.endswith("/artifact"):
            answer = self.artifact_answers.pop(0) if len(self.artifact_answers) > 1 else self.artifact_answers[0]
            if isinstance(answer, Exception):
                raise answer
            return answer
        run_id = path.rsplit("/", 1)[1]
        status = self.run_status[run_id]
        return httpx.Response(200, json={
            "id": run_id, "report": "groups", "cluster": {"r-crc": "crc-local", "r-east": "prod-east"}[run_id],
            "status": status, "sha256": "ab" * 32 if status == "done" else None,
            "finished_at": "2026-10-04T02:00:07Z", "bytes": {"json": 900, "html": 19} if status == "done" else {},
            "error": None if status == "done" else "render failed: KeyError"})


@pytest.fixture
def lab(monkeypatch, tmp_path):
    real = httpx.Client    # taken once: a second build in one test must not wrap the first one's patch

    def build(*extra: str, **kw):
        state = _Lab(**kw)

        def client(**options):
            options.pop("verify", None)    # the transport is the network; there is no TLS to verify
            return real(transport=httpx.MockTransport(state), **options)

        monkeypatch.setattr(trigger.httpx, "Client", client)
        monkeypatch.setattr(trigger.time, "sleep", lambda s: state.__dict__.setdefault("sleeps", []).append(s))
        token = tmp_path / "token"
        token.write_text("service-token")
        url_file = tmp_path / "url"
        url_file.write_text(HOOK + "\n")    # a Secret's value often ends in a newline
        argv = ["--url", SERVICE, "--report", "groups", "--schedule", "weekly", "--token-file", str(token),
                "--wait", "--deliver", "webhook", "--webhook-url-file", str(url_file), *extra]
        state.rc = trigger.main(argv)
        return state
    return build


def _no_url(out: str) -> None:
    for piece in (HOOK, "hooks.receiver.test", "T0SECRET", "xoxSECRETPATH"):
        assert piece not in out, f"the webhook URL leaked ({piece!r})"


@pytest.mark.parametrize("option", ["--format", "--attach"])
def test_schedule_trigger_refuses_pdf(option, lab, capsys):
    with pytest.raises(SystemExit) as exc:
        lab(option, "pdf")
    assert exc.value.code == 2
    assert f"argument {option}: invalid choice: 'pdf'" in capsys.readouterr().err


def test_t109_1_each_finished_run_of_the_fan_out_is_delivered_as_one_event(lab, capsys):
    state = lab()
    out = capsys.readouterr()
    assert state.rc == 0, out.err
    assert [e["id"] for e in state.events] == ["r-crc", "r-east"]
    event = state.events[0]
    assert {k: event[k] for k in ("specversion", "type", "source", "time", "datacontenttype")} == {
        "specversion": "1.0", "type": trigger.EVENT_TYPE, "source": SERVICE,
        "time": "2026-10-04T02:00:07Z", "datacontenttype": "application/json"}
    assert event["data"] == {"report": "groups", "cluster": "crc-local", "run_id": "r-crc", "status": "done",
                             "schedule": "weekly", "sha256": "ab" * 32, "finished_at": "2026-10-04T02:00:07Z",
                             "bytes": {"json": 900, "html": 19}, "error": None}
    assert state.hook_headers[0]["content-type"] == "application/cloudevents+json; charset=utf-8"
    assert "authorization" not in state.hook_headers[0], "the receiver never sees the service token"
    assert out.out.count('"delivered"') == 2
    _no_url(out.out + out.err)


def test_t109_2_attach_sends_the_artefact_base64_and_names_what_it_cannot_send(lab, capsys):
    state = lab("--attach", "html")
    assert state.rc == 0
    attachment = state.events[0]["data"]["attachment"]
    assert base64.b64decode(attachment["content_base64"]) == b"<html>report</html>"
    assert attachment["media_type"] == "text/html; charset=utf-8" and attachment["bytes"] == 19
    state = lab("--attach", "csv")
    assert state.events[0]["data"]["attachment"] == {"format": "csv", "omitted": "this run stored no csv"}


def test_t109_2b_an_attachment_transport_failure_is_omitted_and_the_fan_out_continues(lab):
    state = lab("--attach", "html", artifact_answers=[
        httpx.ConnectError("service GET failed"),
        httpx.Response(200, content=b"<html>report</html>",
                       headers={"content-type": "text/html; charset=utf-8"}),
    ])
    assert state.rc == 0 and [event["id"] for event in state.events] == ["r-crc", "r-east"]
    assert state.events[0]["data"]["attachment"] == {
        "format": "html", "omitted": "the artefact read failed (ConnectError)"}
    assert base64.b64decode(state.events[1]["data"]["attachment"]["content_base64"]) == b"<html>report</html>"


def test_t109_2c_the_response_bytes_cannot_bypass_the_attachment_cap(lab):
    too_large = b"x" * (trigger.ATTACH_MAX_BYTES + 1)
    state = lab("--attach", "html", artifact_answers=[
        httpx.Response(200, content=too_large, headers={"content-type": "text/html"})])
    assert state.rc == 0
    assert state.events[0]["data"]["attachment"] == {
        "format": "html",
        "omitted": f"{len(too_large)} bytes read is over the {trigger.ATTACH_MAX_BYTES}-byte cap",
    }


def test_t109_3_a_failed_post_retries_the_retryable_and_prints_the_status_never_the_url(lab, capsys):
    state = lab(hook_answers=[httpx.Response(503, headers={"Retry-After": "7"}), httpx.Response(200)])
    out = capsys.readouterr()
    assert state.rc == 0 and len(state.events) == 3, "r-crc took two attempts, r-east one"
    assert state.sleeps.count(7.0) == 1, "the receiver's Retry-After is honoured (the other sleeps are the 2 s polls)"
    assert "HTTP 503" in out.err
    _no_url(out.out + out.err)


def test_t109_3b_no_delivery_attempt_starts_at_or_after_the_deadline(monkeypatch):
    now = [10.0]
    starts = []

    class Hook:
        def post(self, *args, **kwargs):
            starts.append(now[0])
            return httpx.Response(503)

    monkeypatch.setattr(trigger.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(trigger.random, "uniform", lambda low, high: 0.0)
    monkeypatch.setattr(trigger.time, "sleep", lambda delay: now.__setitem__(0, 20.0))
    assert trigger._deliver(Hook(), HOOK, {"id": "r"}, deadline=10.0) is False
    assert starts == []

    now[0] = 0.0
    assert trigger._deliver(Hook(), HOOK, {"id": "r"}, deadline=11.0) is False
    assert starts == [0.0], "an oversleep must not start the promised retry after the deadline"


def test_t109_3c_docs_name_the_exact_retryable_statuses():
    root = Path(__file__).resolve().parents[2]
    exact = "408, 429, 500, 502, 503, 504"
    for relative in ("charts/group-sync-dashboard/README.md", "charts/group-sync-dashboard/values.yaml",
                     "charts/group-sync-dashboard/Chart.yaml", "docs/CHANGELOG.md", "docs/specs/README.md"):
        text = (root / relative).read_text()
        assert "408, 429, 5xx" not in text, relative
        assert exact in text, relative


def test_t109_4_an_undelivered_run_fails_the_job_and_a_4xx_is_not_retried(lab, capsys):
    state = lab(hook_answers=[httpx.Response(404)])
    out = capsys.readouterr()
    assert state.rc == 1, "a run that was not delivered fails the Job"
    assert len(state.events) == 2, "404 is not retried: one attempt per run"
    assert out.err.count("delivery failed for run") == 2 and "HTTP 404 after 1 attempt(s)" in out.err
    _no_url(out.out + out.err)


def test_t109_5_a_transport_error_is_retried_then_named_by_its_class_only(lab, capsys):
    # A TLS failure's str() names the host (SPEC_F4 §2.3): the class is all that is printed.
    tls = httpx.ConnectError("certificate is not valid for 'hooks.receiver.test'")
    state = lab(hook_answers=[tls])
    out = capsys.readouterr()
    assert state.rc == 1
    assert len(state.events) == 2 * trigger.DELIVER_ATTEMPTS
    assert f"ConnectError after {trigger.DELIVER_ATTEMPTS} attempt(s)" in out.err
    assert all(0 <= s <= trigger.DELIVER_BACKOFF_CAP_SECONDS for s in state.sleeps)
    _no_url(out.out + out.err)


def test_t109_6_a_failed_run_is_delivered_with_its_error_and_still_fails_the_job(lab, capsys):
    state = lab("--attach", "html", run_status={"r-crc": "done", "r-east": "failed"})
    assert state.rc == 1, "exit 1 when any run failed, delivered or not"
    failed = state.events[1]["data"]
    assert failed["status"] == "failed" and failed["error"] == "render failed: KeyError" and "attachment" not in failed


def test_t109_7_a_window_skip_delivers_nothing_and_exits_0(lab, capsys):
    state = lab(create_status=409)
    assert state.rc == 0 and state.events == []
    assert '"skipped"' in capsys.readouterr().out


def test_t109_8_a_bad_url_file_or_no_wait_is_refused_before_any_run_is_requested(monkeypatch, tmp_path, capsys):
    calls = []
    monkeypatch.setattr(trigger.httpx, "Client", lambda **kw: calls.append(kw))
    token = tmp_path / "token"
    token.write_text("t")
    base = ["--url", SERVICE, "--report", "groups", "--schedule", "weekly", "--token-file", str(token),
            "--deliver", "webhook"]
    assert trigger.main([*base, "--webhook-url-file", str(tmp_path / "absent"), "--wait"]) == 1
    bad = tmp_path / "bad"
    bad.write_text("ftp://hooks.receiver.test/" + SECRET_PART)
    assert trigger.main([*base, "--webhook-url-file", str(bad), "--wait"]) == 1
    good = tmp_path / "good"
    good.write_text(HOOK)
    assert trigger.main([*base, "--webhook-url-file", str(good)]) == 1, "delivery needs --wait"
    assert calls == [], "nothing was requested"
    _no_url(capsys.readouterr().err)


def test_t109_9_the_report_service_makes_no_outbound_call():
    """Delivery belongs to the schedule Job alone (DESIGN_reporting_output_and_delivery.md §4): no module the
    service runs imports an HTTP or mail client, and none imports the trigger."""
    clients = {"httpx", "requests", "urllib.request", "http.client", "socket", "smtplib", "aiohttp"}
    for path in sorted(REPORTING.rglob("*.py")):
        if path.name == "trigger.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(), str(path))):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                     else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            for name in names:
                assert name not in clients and not name.endswith("trigger"), (path.name, name)


# ── OB3 review of #109: a hostile Retry-After, the deadline, the URL file, the event's time, the docs ──


def test_review_a_non_ascii_digit_retry_after_falls_back_to_backoff(lab, capsys):
    # '²'.isdigit() is True and float('²') raises: httpx decodes the byte 0xB2 as latin-1 '²'.
    state = lab(hook_answers=[httpx.Response(503, headers=[(b"Retry-After", b"\xb2")]), httpx.Response(200)])
    out = capsys.readouterr()
    assert state.rc == 0 and len(state.events) == 3, "r-crc retried once on jitter, r-east delivered"
    _no_url(out.out + out.err)


def test_review_no_attempt_starts_that_cannot_finish_before_the_deadline(capsys):
    posts = []
    with httpx.Client(transport=httpx.MockTransport(lambda r: posts.append(r) or httpx.Response(200))) as hook:
        assert trigger._deliver(hook, HOOK, {"id": "r-late"}, trigger.time.monotonic() + 1) is False
    assert posts == [], "the first attempt is held to the deadline like a retry"
    err = capsys.readouterr().err
    assert "delivery failed for run r-late" in err
    _no_url(err)


def test_review_a_url_file_that_is_not_utf8_is_refused_by_class(tmp_path, capsys):
    bad = tmp_path / "url"
    bad.write_bytes(HOOK.encode() + b"\xff")
    assert trigger._webhook_url(str(bad)) is None
    err = capsys.readouterr().err
    assert "cannot be read (UnicodeDecodeError)" in err
    _no_url(err)


def test_review_a_run_without_finished_at_sends_no_null_time():
    # artifacts.py: a run the service restarted under is `failed` with finished_at None.
    event = trigger._event({"id": "r1", "status": "failed", "finished_at": None, "error": "restarted"}, "w", SERVICE, None)
    assert "time" not in event and event["data"]["finished_at"] is None


def test_review_the_docs_name_the_statuses_the_trigger_retries():
    root = Path(__file__).resolve().parents[2]
    texts = {
        "README row": next(line for line in (root / "charts/group-sync-dashboard/README.md").read_text().splitlines()
                           if line.startswith("| `reporting.schedules[].deliver`")),
        "values comment": (root / "charts/group-sync-dashboard/values.yaml").read_text().split("# `deliver` (#109")[1][:900],
        "CHANGELOG bullet": (root / "docs/CHANGELOG.md").read_text().split("**Webhook delivery of scheduled reports")[1][:900],
    }
    for where, text in texts.items():
        assert "5xx" not in text, f"{where}: the trigger retries {sorted(trigger.RETRYABLE_STATUSES)}, not every 5xx"
        assert all(str(code) in text for code in trigger.RETRYABLE_STATUSES), where
        assert "four times" not in text and "4 times" not in text, f"{where}: 4 attempts are 3 retries"
