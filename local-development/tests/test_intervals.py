"""Chart 0.56.0: bindings refresh hourly, cluster discovery keeps its own five-minute timer.

Discovery rode `bindingIntervalSeconds` until then, so slowing the bindings would have delayed a
cluster applied with oc or GitOps by up to an hour (the operator, 2026-09-25: discovery "should run
on a different timer and parameters"). These pin the split at all three places the key lives:
the loader, the discovery thread and the chart."""
from __future__ import annotations

import subprocess

import pytest
import yaml

from gsd.config import ClusterConfig, ConfigError, Settings, load_settings
from gsd.poller import Poller
from gsd.store import Store
from test_chart_strategy import CHART

BASE = """
clusters:
  - name: crc-local
    apiUrl: https://api.crc.testing:6443
    tokenEnv: GSD_TOKEN_CRC
"""


def _load(tmp_path, extra=""):
    p = tmp_path / "clusters.yaml"
    p.write_text(BASE + extra)
    return load_settings(str(p))


def test_the_defaults_are_hourly_bindings_and_five_minute_discovery(tmp_path):
    s = _load(tmp_path)
    assert (s.binding_interval_seconds, s.discovery_interval_seconds) == (3600, 300)


def test_each_interval_is_read_on_its_own(tmp_path):
    s = _load(tmp_path, "bindingIntervalSeconds: 7200\ndiscoveryIntervalSeconds: 120\n")
    assert (s.binding_interval_seconds, s.discovery_interval_seconds) == (7200, 120)


def test_the_discovery_thread_waits_on_the_discovery_interval_not_the_binding_one(tmp_path):
    settings = Settings(clusters=[ClusterConfig("host", "https://kubernetes.default.svc", token_env="X")],
                        db_path=str(tmp_path / "p.db"), binding_interval_seconds=3600, discovery_interval_seconds=7)
    poller = Poller(Store(str(tmp_path / "p.db")), settings)
    waits = []

    def wait(timeout):
        waits.append(timeout)
        poller._stop.set()        # one iteration: the loop returns before discovering
        return False
    poller._discover_now.wait = wait
    poller._run_discovery()
    assert waits == [7]


def test_the_chart_renders_both_keys_into_the_configmap(tmp_path):
    values = tmp_path / "v.yaml"
    values.write_text(yaml.safe_dump({"config": {"discoveryIntervalSeconds": 90}}))
    for extra, expected in (([], (3600, 300)), (["-f", str(values)], (3600, 90))):
        done = subprocess.run(["helm", "template", "t", str(CHART), "--show-only", "templates/configmap.yaml",
                               "--set", "ingress.host=t.example.com", *extra], capture_output=True, text=True)
        assert done.returncode == 0, done.stderr
        config = yaml.safe_load(yaml.safe_load(done.stdout)["data"]["clusters.yaml"])
        assert (config["bindingIntervalSeconds"], config["discoveryIntervalSeconds"]) == expected


def test_a_discovery_interval_below_one_is_refused_by_the_loader(tmp_path):
    """0 is Event.wait(0): a busy loop of host LISTs and a zero lookup backoff (review of #368, Grok C6)."""
    for value in ("0", "-1"):
        with pytest.raises(ConfigError, match="discoveryIntervalSeconds must be at least 1"):
            _load(tmp_path, f"discoveryIntervalSeconds: {value}\n")
    assert _load(tmp_path, "discoveryIntervalSeconds: 1\n").discovery_interval_seconds == 1


def test_the_chart_refuses_a_discovery_interval_below_one():
    done = subprocess.run(["helm", "template", "t", str(CHART), "--show-only", "templates/configmap.yaml",
                           "--set", "ingress.host=t.example.com", "--set", "config.discoveryIntervalSeconds=0"],
                          capture_output=True, text=True)
    assert done.returncode != 0 and "discoveryIntervalSeconds must be at least 1" in done.stderr
