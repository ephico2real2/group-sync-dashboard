"""The e2e walk's second-cluster step must skip the Overview's fleet option (#172): its value is empty
and its label is "all clusters", and choosing options by label kept the walk on the fleet while it
recorded "switch cluster to all clusters" as the second cluster's evidence (Codex, review of #172,
pass 2)."""
from __future__ import annotations

import importlib.util
import pathlib


def _capture_module():
    path = pathlib.Path(__file__).resolve().parents[1] / "e2e-walk" / "e2e_capture.py"
    spec = importlib.util.spec_from_file_location("gsd_e2e_capture", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_walk_skips_the_fleet_option_when_choosing_the_second_cluster():
    pick = _capture_module().next_configured_cluster
    options = [{"value": "", "label": "all clusters"},
               {"value": "crc-local", "label": "crc-local"},
               {"value": "prod-east", "label": "prod-east"}]
    assert pick(options, "") == options[2]
    assert pick(options, "crc-local") == options[2]
    assert pick(options, "prod-east") == options[1]
    assert pick([{"value": "", "label": "all clusters"}], "") is None
    assert pick([{"value": "", "label": "all clusters"}, {"value": "only", "label": "only"}], "") == {"value": "only", "label": "only"}
