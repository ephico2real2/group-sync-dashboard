"""Every schedule environments/crc.yaml declares must FIRE INSIDE the lab's reporting window.

WHY. The report service answers an automated run outside the window with 409, and the CronJob's
trigger records that as a skip with exit 0 (gsd/reporting/trigger.py) — so a schedule whose cron lands
outside the window never produces a report and nothing fails. The window is half-open [start, end)
(gsd/reporting/window.py `contains`), so a 06:00 fire against a 22:00-06:00 window is OUTSIDE it.
Paused schedules are checked too: resuming one must not start a silent skip.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

from gsd.reporting import cron
from gsd.reporting.window import ReportingWindow

CRC = Path(__file__).resolve().parents[2] / "environments" / "crc.yaml"
REPORTING = yaml.safe_load(CRC.read_text())["reporting"]
WINDOW = ReportingWindow.from_strings(**{k: REPORTING["window"][k] for k in ("enabled", "timezone", "start", "end", "days")})


@pytest.mark.parametrize("schedule", REPORTING["schedules"], ids=lambda s: s["name"])
def test_every_crc_schedule_fires_inside_the_window(schedule):
    spec = cron.parse(schedule["schedule"])
    at = datetime(2026, 1, 1, tzinfo=UTC)
    outside = []
    for _ in range(12):  # 3 years of the quarterly, 6 months of the 1st/16th, the weekly across March's DST change
        at = cron.next_fire(spec, at, WINDOW.timezone)
        assert at is not None, f"{schedule['name']}: {schedule['schedule']!r} never fires"
        if not WINDOW.is_open(at):
            outside.append(at.astimezone(ZoneInfo(WINDOW.timezone)).isoformat())
    assert not outside, f"{schedule['name']} ({schedule['schedule']!r}) fires outside the window at {outside}"
