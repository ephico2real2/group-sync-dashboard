"""#249 second pass (review of PR #251): the chart's render-time guard and NOTES must find the
host the way load_settings does — the declared `dashboardController`, else the first enabled
entry — and refuse at `helm template` the three values the pod refuses at startup, so a bad flag
fails the render rather than a green upgrade that crash-loops. Pure Helm: CI's chart job runs
this file without the application installed."""
from __future__ import annotations

import subprocess

import pytest
import yaml

from test_chart_route import _notes_probe_chart
from test_chart_strategy import CHART


def _render_values(tmp_path, clusters: list[dict], chart=CHART, select: str | None = None, values: dict | None = None):
    values_file = tmp_path / "values.yaml"
    values_file.write_text(yaml.safe_dump({"clusters": clusters, **(values or {})}, sort_keys=False))
    values = values_file
    args = ["helm", "template", "t", str(chart), "-f", str(values), "--set", "ingress.host=t.example.com"]
    if select:
        args += ["-s", select]
    done = subprocess.run(args, capture_output=True, text=True)
    return done.returncode == 0, done.stdout + done.stderr


EAST = {"name": "ocp-east", "apiUrl": "https://api.east.example.com:6443", "tokenEnv": "T"}
HOME = {"name": "home", "apiUrl": "https://kubernetes.default.svc", "tokenEnv": "T", "dashboardController": True}


class TestTheGuardFollowsTheDeclaredController:
    def test_hidden_on_a_declared_controller_that_is_not_first_is_refused(self, tmp_path):
        ok, out = _render_values(tmp_path, [EAST, {**HOME, "visibility": "hidden"}])
        assert not ok and "clusters[1] (home) is the hosting cluster — declared by dashboardController: true" in out

    def test_the_first_entry_is_a_remote_when_another_declares_the_controller(self, tmp_path):
        ok, out = _render_values(tmp_path, [{**EAST, "visibility": "hidden"}, HOME])
        assert ok, out

    def test_two_declared_controllers_are_refused_by_name(self, tmp_path):
        ok, out = _render_values(tmp_path, [{**EAST, "dashboardController": True}, HOME])
        assert not ok and "2 clusters declare dashboardController (ocp-east, home)" in out

    def test_a_declared_but_disabled_controller_is_refused(self, tmp_path):
        ok, out = _render_values(tmp_path, [EAST, {**HOME, "enabled": False}])
        assert not ok and "clusters[1] (home) is the dashboardController but enabled is false" in out

    @pytest.mark.parametrize("word", ("yes", "1"))
    def test_a_non_boolean_flag_is_refused(self, tmp_path, word):
        ok, out = _render_values(tmp_path, [{**HOME, "dashboardController": word}])
        assert not ok and "clusters[0] (home): dashboardController must be true or false" in out

    def test_without_the_flag_the_first_enabled_entry_is_still_the_host(self, tmp_path):
        east, home = dict(EAST), {k: v for k, v in HOME.items() if k != "dashboardController"}
        ok, out = _render_values(tmp_path, [{**east, "visibility": "hidden"}, home])
        assert not ok and "clusters[0] (ocp-east) is the hosting cluster — the first enabled entry" in out


class TestNotesPrintTheDeclaredControllerFirst:
    def test_the_declared_controller_is_printed_as_the_host_even_when_second(self, tmp_path, tmp_path_factory):
        probe = _notes_probe_chart(tmp_path_factory.mktemp("notes-249"))
        ok, out = _render_values(tmp_path, [EAST, HOME], chart=probe, select="templates/notes-probe.yaml")
        assert ok, out
        lines = [l.strip() for l in out.splitlines() if l.strip().startswith(("ocp-east:", "home:"))]
        assert lines == ["home: visibility inherit (host), identity same-as-host (host)",
                         "ocp-east: visibility remote-sar (default), identity same-as-host (default)"], lines
