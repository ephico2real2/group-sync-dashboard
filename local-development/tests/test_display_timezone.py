"""Times are shown in the container's timezone, and the wire stays UTC.

The dashboard used to render UTC while the logs were stamped in the container's local zone,
so the same screen disagreed with the log line describing it and correlating the two was
arithmetic. Now both use the zone `TZ` names.

Two invariants pull in opposite directions and both matter:

  * DISPLAY is local, so a human reads the same numbers on the page and in the logs;
  * STORAGE AND THE API stay UTC, ending in Z, so the data means one thing regardless of
    where it is read, what TZ a replica happens to have, or whether tzdata is installed.

The conversion belongs at the very edge — in the browser, at render time — and nowhere else.
This file guards the boundary between those two.
"""

from __future__ import annotations

import os
import pathlib
import re
import time

import pytest
from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.config import Settings
from gsd.store import Store
from gsd.timeutil import now_iso

INDEX = pathlib.Path(__file__).resolve().parents[1] / "gsd" / "static" / "index.html"


@pytest.fixture()
def in_new_york():
    """Run the server as if the container had TZ=America/New_York."""
    before = os.environ.get("TZ")
    os.environ["TZ"] = "America/New_York"
    time.tzset()
    yield
    if before is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = before
    time.tzset()


def _client(tmp_path) -> TestClient:
    return TestClient(
        build_app(Settings(db_path=str(tmp_path / "t.db"), clusters=[]), run_poller=False)
    )


def test_the_api_reports_the_container_timezone(tmp_path, in_new_york):
    """The browser cannot discover the SERVER's zone on its own — it only knows its own."""
    tz = _client(tmp_path).get("/api/version").json()["timezone"]
    assert tz["name"] == "America/New_York"
    assert tz["abbrev"] in {"EST", "EDT"}
    assert re.fullmatch(r"[+-]\d{4}", tz["utc_offset"]), tz["utc_offset"]
    assert tz["utc_offset"] != "+0000", (
        "offset resolved to UTC with TZ set — tzdata is probably missing, which makes TZ "
        "parse as a POSIX spec and silently mean UTC"
    )


def test_no_timezone_is_reported_as_none_rather_than_guessed(tmp_path):
    """With TZ unset the browser must fall back to UTC explicitly, not infer a zone."""
    before = os.environ.pop("TZ", None)
    time.tzset()
    try:
        assert _client(tmp_path).get("/api/version").json()["timezone"]["name"] is None
    finally:
        if before is not None:
            os.environ["TZ"] = before
        time.tzset()


def test_stored_timestamps_stay_utc_whatever_tz_says(tmp_path, in_new_york):
    """The load-bearing one. A local timestamp in the database is a silent corruption.

    Every write goes through datetime.now(UTC), so TZ cannot move it. If this ever fails,
    rows written before and after a TZ change mean different things and nothing in the data
    says which is which.
    """
    store = Store(str(tmp_path / "tz.db"))
    store.upsert_cluster("c1", "https://x", True)
    store.record_poll("c1", "ok", None)
    stamp = now_iso()
    store.close()

    assert stamp.endswith("Z"), stamp
    # 21:xx UTC is 17:xx in New York — if the stored hour were local, this would differ.
    assert stamp[11:13] == time.strftime("%H", time.gmtime()), (
        "now_iso() drifted to local time"
    )


def test_the_api_serves_utc_not_local(tmp_path, in_new_york):
    """Conversion happens in the browser. An API that emitted local time would force every
    other consumer — curl, a script, a future report — to reverse-engineer the zone."""
    client = _client(tmp_path)
    store = Store(str(tmp_path / "t.db"))
    store.upsert_cluster("c1", "https://x", True)
    store.record_poll("c1", "ok", None)
    store.close()

    for row in client.get("/api/clusters").json():
        for key, value in row.items():
            if isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}T", value):
                assert value.endswith("Z"), f"{key} is not UTC: {value}"


def test_the_page_labels_every_absolute_time_with_its_zone():
    """An unlabelled wall clock is ambiguous, and this page sits beside `oc` output.

    fmtTime is the single formatter, so checking it is enough — the label is appended in
    both branches, the UTC fallback and the zoned one.
    """
    html = INDEX.read_text()
    body = html[html.index("function fmtTime"):]
    body = body[:body.index("\nfunction ")]
    assert "displayAbbrev" in body, "the zoned branch does not append a zone label"
    assert 'replace("T", " ")' in body, "the UTC fallback branch is missing"


def test_the_page_falls_back_to_utc_when_the_zone_is_unusable():
    """An IANA name the browser does not know makes Intl throw.

    A page that throws on its first timestamp renders nothing, and the two newest tabs are
    opened by no browser test — precisely how two bugs hid here before. The formatter is
    therefore wrapped, and unusable means UTC rather than blank.
    """
    html = INDEX.read_text()
    fn = html[html.index("function setDisplayZone"):]
    fn = fn[:fn.index("\n/* Absolute time")]
    assert "try {" in fn and "catch" in fn, "setDisplayZone does not guard against Intl throwing"
    assert 'displayAbbrev = "Z"' in fn, "no UTC fallback on an unusable zone"


def test_the_usage_day_column_says_it_is_utc():
    """Display is local but the day bucket is a stored UTC date, so the page must say so.

    Near midnight a session lands on the following UTC day; unlabelled, that reads as a bug
    in the dashboard rather than a boundary in the data.
    """
    html = INDEX.read_text()
    assert "<th>Day (UTC)</th>" in html, "the Usage day column does not declare its zone"
