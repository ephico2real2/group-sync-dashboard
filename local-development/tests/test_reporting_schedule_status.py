"""#140 item 2: a schedule that silently stops producing evidence raises an alert.

The report service exports the Reporting status page's own verdict per schedule as
`gsd_report_schedule_status{schedule, status}`, and the chart's rule reads `status="late"`. These tests hold the
gauge to the page (one computation, so they can never disagree), the rule's render to its two switches, and the
rule's expression to Prometheus's own evaluator (`promtool test rules`). SPEC_F5 §4."""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from datetime import UTC, datetime

import pytest
import yaml
from fastapi.testclient import TestClient

from gsd.reporting import REPORT_PREFIX
from gsd.reporting.artifacts import ArtifactStore, Run
from gsd.reporting.config import ReportSettings
from gsd.reporting.metrics import SCHEDULE_STATES
from gsd.reporting.ticket import mint
# the report service with its two secrets apart (#392): test_reporting_server's builder holds the ticket key
from test_reporting_server import TICKET_KEY, build_report_app
from gsd.activity import USER_HEADER
from gsd.reporting import TICKET_HEADER
from reporting_seed import CLUSTER, seeded_dirs
from test_chart_pdb import CHART, _render

SECRET = b"s" * 48
SERVICE = {"Authorization": f"Bearer {SECRET.decode()}"}
VENDOR = CHART.parents[1] / "local-development" / "gsd" / "static" / "vendor"
FONTS = (str(VENDOR / "DejaVuSans.ttf"), str(VENDOR / "DejaVuSans-Bold.ttf"))
ALERT = "GroupSyncDashboardReportScheduleLate"

#: One schedule per page state at 2026-09-20 12:00 UTC (no window, so the cron reads UTC):
#: `fresh` succeeded after today's 02:00 fire, `stale` last succeeded yesterday (today's fire is 10 h past),
#: `unrun` has no run on record, `paused` is disabled although it once succeeded.
SCHEDULES = (
    {"name": "fresh", "schedule": "0 2 * * *", "report": "groups"},
    {"name": "stale", "schedule": "0 2 * * *", "report": "groups"},
    {"name": "unrun", "schedule": "0 2 * * *", "report": "groups"},
    {"name": "paused", "schedule": "0 2 * * *", "report": "groups", "enabled": False},
)
EXPECTED = {"fresh": "ok", "stale": "late", "unrun": "never", "paused": "disabled"}


def _done(run_id: str, day: str, schedule: str) -> Run:
    return Run(id=run_id, report="groups", cluster=CLUSTER, params={}, formats=["html"],
               generated_by=f"schedule:{schedule}", generated_by_note="unattended", schedule=schedule,
               origin="schedule", requested_at=f"{day}T02:00:00Z", started_at=f"{day}T02:00:01Z",
               finished_at=f"{day}T02:02:00Z", status="done", sha256="ab" * 32)


def _app(tmp_path, at: datetime, schedules=SCHEDULES, seed=()):
    tmp_path.mkdir(exist_ok=True)
    snapshots, artifacts = seeded_dirs(tmp_path)
    store = ArtifactStore(str(artifacts))
    for r in seed:
        store.create(r)
    settings = ReportSettings(snapshot_dir=str(snapshots), artifact_dir=str(artifacts), pdf_enabled=True,
                              pdf_variant="pdf/a-2b", font_regular=FONTS[0], font_bold=FONTS[1],
                              login_capture_enabled=True, schedules=schedules, max_queued_runs=0)
    return build_report_app(settings, secret=SECRET, clock=lambda: at)


def _status_series(metrics_text: str) -> dict[str, dict[str, float]]:
    """{schedule: {status: value}} from the exposition's gsd_report_schedule_status lines."""
    out: dict[str, dict[str, float]] = {}
    for line in metrics_text.splitlines():
        if line.startswith("gsd_report_schedule_status{"):
            labels, value = line.rsplit(" ", 1)
            pairs = dict(p.split("=", 1) for p in labels[len("gsd_report_schedule_status{"):-1].split(","))
            out.setdefault(pairs["schedule"].strip('"'), {})[pairs["status"].strip('"')] = float(value)
    return out


SEED = (_done("20260919T020000.000000Z-0001", "2026-09-19", "stale"),
        _done("20260919T020000.000000Z-0002", "2026-09-19", "fresh"),
        _done("20260920T020000.000000Z-0003", "2026-09-20", "fresh"),
        _done("20260919T020000.000000Z-0004", "2026-09-19", "paused"))


class TestTheGaugeIsThePagesVerdict:
    def test_t140_1_each_schedule_exports_the_state_the_page_shows_for_ok_late_never_and_disabled(self, tmp_path):
        with TestClient(_app(tmp_path, datetime(2026, 9, 20, 12, 0, tzinfo=UTC), seed=SEED)) as client:
            page = {s["name"]: s["status"] for s in client.get(f"{REPORT_PREFIX}/api/status", headers=SERVICE).json()["schedules"]}
            series = _status_series(client.get(f"{REPORT_PREFIX}/metrics").text)
        assert page == EXPECTED, page                                  # the four states, as the page has always read them
        assert set(series) == set(EXPECTED), series
        for name, state in page.items():
            assert series[name] == {s: (1.0 if s == state else 0.0) for s in SCHEDULE_STATES}, (name, series[name])

    def test_t140_2_the_gauge_turns_late_with_the_page_at_the_thirty_minute_grace(self, tmp_path):
        stale_only = (SCHEDULES[1],)
        seed = (SEED[0],)
        for i, (at, state) in enumerate(((datetime(2026, 9, 20, 2, 29, tzinfo=UTC), "ok"),
                                         (datetime(2026, 9, 20, 2, 31, tzinfo=UTC), "late"))):
            with TestClient(_app(tmp_path / str(i), at, schedules=stale_only, seed=seed)) as client:
                page = client.get(f"{REPORT_PREFIX}/api/status", headers=SERVICE).json()["schedules"][0]["status"]
                series = _status_series(client.get(f"{REPORT_PREFIX}/metrics").text)["stale"]
            assert page == state and series[state] == 1.0 and sum(series.values()) == 1.0, (at, page, series)

    def test_t140_3_no_schedule_no_series_and_the_family_is_still_declared(self, tmp_path):
        with TestClient(_app(tmp_path, datetime(2026, 9, 20, 12, 0, tzinfo=UTC), schedules=())) as client:
            text = client.get(f"{REPORT_PREFIX}/metrics").text
        assert "# TYPE gsd_report_schedule_status gauge" in text
        assert not _status_series(text)


class TestMustNotChange:
    def test_t140_4_the_last_success_gauge_keeps_its_name_and_label_and_no_person_is_named(self, tmp_path):
        at = datetime.fromtimestamp(int(time.time()), UTC)            # a ticket is checked against the real clock
        with TestClient(_app(tmp_path, at, seed=SEED)) as client:
            ticket = {TICKET_HEADER: mint(TICKET_KEY, "alice.person", "all", 300), USER_HEADER: "alice.person"}
            assert client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "groups", "cluster": CLUSTER},
                               headers=ticket).status_code == 202
            text = client.get(f"{REPORT_PREFIX}/metrics").text
        last = [ln for ln in text.splitlines() if ln.startswith("gsd_report_schedule_last_success_timestamp{")]
        assert sorted(ln.split("}")[0] for ln in last) == sorted(
            f'gsd_report_schedule_last_success_timestamp{{schedule="{n}"' for n in ("fresh", "paused", "stale"))
        assert "alice.person" not in text, "/metrics is unauthenticated: no viewer's name in any series"
        status_lines = [ln for ln in text.splitlines() if ln.startswith("gsd_report_schedule_status{")]
        assert len(status_lines) == len(SCHEDULES) * len(SCHEDULE_STATES)
        assert all(ln.split("{")[1].split("=")[0] == "schedule" and ',status="' in ln for ln in status_lines)


def _rule(docs: list[dict]) -> dict | None:
    hits = [r for d in docs if d.get("kind") == "PrometheusRule" for g in d["spec"]["groups"] for r in g["rules"]
            if r.get("alert") == ALERT]
    assert len(hits) <= 1
    return hits[0] if hits else None


class TestTheRule:
    def test_t140_5_the_rule_renders_only_with_the_rules_and_reporting_on(self):
        on = _rule(_render())                                          # both on by default (values.yaml)
        assert on is not None
        assert on["expr"] == 'max by (schedule) (gsd_report_schedule_status{status="late"}) == 1'
        assert on["for"] == "15m" and on["labels"] == {"severity": "warning"}
        assert "{{ $labels.schedule }}" in on["annotations"]["summary"]
        assert "t-group-sync-dashboard-report-{{ $labels.schedule }}" in on["annotations"]["description"]
        assert _rule(_render("monitoring.prometheusRule.for.reportScheduleLate=45m"))["for"] == "45m"
        assert _rule(_render("monitoring.prometheusRule.enabled=false")) is None
        assert _rule(_render("reporting.enabled=false")) is None

    def test_t140_5b_the_readme_values_row_counts_the_rendered_alerts(self):
        """The README's `monitoring.prometheusRule.enabled` row restates the rule count, a second copy of it:
        this rule is the third that renders only with reporting on, so the row must say so (#140)."""
        def alerts(*sets):
            return [r for d in _render(*sets) if d.get("kind") == "PrometheusRule" for g in d["spec"]["groups"]
                    for r in g["rules"] if "alert" in r]
        total = len(alerts())
        assert (total, total - len(alerts("reporting.enabled=false"))) == (20, 3)
        row = next(ln for ln in (CHART / "README.md").read_text().splitlines()
                   if ln.startswith("| `monitoring.prometheusRule.enabled` |"))
        assert "**twenty** alerts — three of them render only with `reporting.enabled`" in row, row

    def test_t140_6_promtool_fires_on_late_only_once_per_schedule_after_for(self, tmp_path):
        """Prometheus's own evaluator over the rendered rule. Skips locally without promtool; CI installs it
        (ci.yml, "Install promtool") and must run it, as the board's PromQL test does."""
        promtool = shutil.which("promtool")
        if promtool is None:
            if os.environ.get("CI"):
                pytest.fail("CI must install promtool; the rule's unit test must not skip there")
            pytest.skip("promtool not installed")
        rule = _rule(_render())
        (tmp_path / "rules.yaml").write_text(yaml.safe_dump({"groups": [{"name": "f5", "rules": [rule]}]}))
        (tmp_path / "test.yaml").write_text(yaml.safe_dump(PROMTOOL_TEST, sort_keys=False))
        done = subprocess.run([promtool, "test", "rules", "test.yaml"], cwd=tmp_path,
                              capture_output=True, text=True, timeout=120)
        assert done.returncode == 0, done.stdout + done.stderr


def _late(schedule: str, values: str, pod: str = "report-0") -> dict:
    return {"series": f'gsd_report_schedule_status{{schedule="{schedule}",status="late",pod="{pod}"}}', "values": values}


#: The one alert `stale` raises: one per schedule, whichever pod exported it.
FIRING = [{
    "exp_labels": {"schedule": "stale", "severity": "warning"},
    "exp_annotations": {
        "summary": "report schedule stale has produced no evidence since its last expected fire",
        "description": ("The Reporting status page reads stale as late: its last expected fire is more than 30 minutes "
                        "past and no run of it has succeeded since. Check its runs on the Report history, the CronJob "
                        "t-group-sync-dashboard-report-stale (its spec.timeZone against reporting.window.timezone, its "
                        "last Job's log), and the report pod's log."),
    }}]

#: One-minute steps. `stale` reads late from minute 0, so the alert is pending until `for` (15m) and firing
#: after; it is scraped from two pods for the first 20 minutes (a rollout) and still alerts once. `fresh`,
#: `unrun` and `paused` export late=0 throughout (they are ok, never and disabled), so they never fire.
PROMTOOL_TEST = {
    "rule_files": ["rules.yaml"],
    "evaluation_interval": "1m",
    "tests": [{
        "interval": "1m",
        "input_series": [
            _late("stale", "1x40"),
            _late("stale", "1x20", pod="report-1"),
            _late("fresh", "0x40"),
            _late("unrun", "0x40"),
            _late("paused", "0x40"),
        ],
        "alert_rule_test": [
            {"eval_time": "14m", "alertname": ALERT, "exp_alerts": []},
            {"eval_time": "16m", "alertname": ALERT, "exp_alerts": FIRING},
            {"eval_time": "30m", "alertname": ALERT, "exp_alerts": FIRING},
        ],
    }],
}
