"""The report model: the sha256 is over the DATA and only the data (docs/specs/SPEC_C3_reporting_microservice.md §9.4)."""
from __future__ import annotations

import json

from gsd.reporting.model import KeyValues, Note, Report, Section, Table


def _report(**over) -> Report:
    base = dict(name="groups", title="Groups", cluster="crc", api_url="https://x", generated_at="2026-09-06T00:00:00Z",
                generated_by="root", generated_by_note="proxy-verified", run_id="r1", params={"window_days": 30},
                coverage={"namespaces_read": "off"}, provenance={"marking": "internal"}, totals={"groups": 1},
                truncated=False, include_members=False,
                sections=[Section("S", [Table("T", ["a", "b"], [["1", "2"]]), KeyValues("K", [("k", "v")]), Note("n")])])
    base.update(over)
    return Report(**base).seal()


def test_the_seal_hashes_the_canonical_data_only():
    a = _report()
    b = _report(generated_at="2030-01-01T00:00:00Z", generated_by="alice", run_id="r2", provenance={"marking": "other"})
    assert a.sha256 == b.sha256, "generated_at, generated_by, run_id and provenance are not data"
    c = _report(sections=[Section("S", [Table("T", ["a", "b"], [["1", "3"]])])])
    assert c.sha256 != a.sha256, "one cell differs"
    assert len(a.sha256) == 64


def test_to_json_round_trips_and_carries_the_hash_and_block_kinds():
    r = _report()
    doc = json.loads(r.to_json())
    assert doc["sha256"] == r.sha256 and doc["run_id"] == "r1" and doc["generated_by"] == "root"
    kinds = [b["kind"] for b in doc["sections"][0]["blocks"]]
    assert kinds == ["table", "kv", "note"]
    assert doc["params"] == {"window_days": 30} and doc["totals"] == {"groups": 1}
