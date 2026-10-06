"""kpi.thresholds are refused at render when the app would refuse them, or when the unit is plainly wrong (#627).

All four are PERCENTAGES: 80 means 80 %, not 0.8. They were written into the ConfigMap unchecked, so a value
the app refuses at startup (`gsd/config.py`: outside (0, 100]) rendered, a string such as "80%" failed the pod
or broke the PrometheusRule's `divf` with a message naming no key, and `cpuPercent: 0.8` — a ratio meant as
80 % — passed every check and alerted at 0.8 %. The render now refuses each of those, naming the key, as
config.alerts.groupCountCliff already is.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest
import yaml

CHART = pathlib.Path(__file__).resolve().parents[2] / "charts" / "group-sync-dashboard"
KEYS = ("memoryPercent", "cpuPercent", "throttledPercent", "diskPercent")

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")


def render(*flags: str) -> subprocess.CompletedProcess:
    return subprocess.run(["helm", "template", "t", str(CHART), *flags], capture_output=True, text=True, timeout=120)


@pytest.mark.parametrize("key", KEYS)
@pytest.mark.parametrize("value", ["0", "-5", "101"])
def test_out_of_range_is_refused_naming_the_key(key: str, value: str) -> None:
    done = render("--set", f"kpi.thresholds.{key}={value}")
    assert done.returncode != 0
    assert f"kpi.thresholds.{key} must be in (0, 100]" in done.stderr, done.stderr


@pytest.mark.parametrize("key", KEYS)
def test_a_string_is_refused_naming_the_key(key: str) -> None:
    done = render("--set-string", f"kpi.thresholds.{key}=80%")
    assert done.returncode != 0
    assert f"kpi.thresholds.{key} must be a number of percent" in done.stderr, done.stderr


@pytest.mark.parametrize("key", ("memoryPercent", "cpuPercent", "diskPercent"))
@pytest.mark.parametrize("value", ["0.8", "1"])
def test_a_ratio_is_refused_for_memory_cpu_and_disk(key: str, value: str) -> None:
    done = render("--set", f"kpi.thresholds.{key}={value}")
    assert done.returncode != 0
    assert f"kpi.thresholds.{key} is {value}, which looks like a ratio" in done.stderr, done.stderr


@pytest.mark.parametrize("flags", [(), ("--set", "kpi.thresholds.throttledPercent=0.5"),
                                   ("--set", "kpi.thresholds.cpuPercent=100"),
                                   ("--set", "kpi.thresholds.diskPercent=1.5")])
def test_valid_values_render(flags: tuple[str, ...]) -> None:
    done = render(*flags)
    assert done.returncode == 0, done.stderr


def test_valid_values_reach_the_configmap_and_the_rules_unchanged() -> None:
    """The guard emits nothing: the ConfigMap keys and the PrometheusRule thresholds are what they were."""
    done = render("--set", "kpi.thresholds.throttledPercent=0.5")
    assert done.returncode == 0, done.stderr
    docs = [d for d in yaml.safe_load_all(done.stdout) if d]
    config = next(d for d in docs if d["kind"] == "ConfigMap" and d["metadata"]["name"] == "t-group-sync-dashboard-config")
    text = next(iter(config["data"].values()))
    for line in ("kpiMemoryWarnPercent: 80", "kpiCpuWarnPercent: 80", "kpiThrottledWarnPercent: 0.5", "kpiDiskWarnPercent: 80"):
        assert line in text, line
    rules = next(d for d in docs if d["kind"] == "PrometheusRule")
    exprs = [r["expr"] for g in rules["spec"]["groups"] for r in g["rules"] if "alert" in r]
    assert any(e.endswith("> 0.005") for e in exprs), exprs
    assert any(e.endswith("> 0.8") for e in exprs), exprs
