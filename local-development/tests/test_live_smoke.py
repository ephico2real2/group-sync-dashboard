"""Smoke test against a real cluster.

Skipped unless GSD_LIVE_CONFIG points at a config whose clusters are reachable, so the
default `pytest` run stays hermetic. Run it with:

    GSD_TOKEN_CRC=$(oc whoami -t) GSD_LIVE_CONFIG=clusters.yaml pytest tests/test_live_smoke.py -v

It asserts the shape of what comes back, not specific counts — group counts change on every
sync, and a test that pinned them would fail for the wrong reason.
"""

from __future__ import annotations

import os

import pytest

from gsd.config import load_settings
from gsd.kube import OK
from gsd.poller import poll_once
from gsd.state import is_valid_schedule
from gsd.store import Store

CONFIG = os.environ.get("GSD_LIVE_CONFIG")

pytestmark = pytest.mark.skipif(
    not CONFIG, reason="set GSD_LIVE_CONFIG to run the live smoke test"
)


@pytest.fixture()
def polled():
    settings = load_settings(CONFIG)
    store = Store(":memory:")
    cluster = settings.clusters[0]
    store.upsert_cluster(cluster.name, cluster.api_url, cluster.enabled)
    outcome = poll_once(store, cluster)
    yield store, cluster, outcome
    store.close()


def test_poll_succeeds(polled):
    _, cluster, outcome = polled
    assert outcome == OK, f"poll of {cluster.name} returned {outcome}"


def test_groupsyncs_are_readable_and_scheduled(polled):
    store, cluster, _ = polled
    crs = store.groupsyncs(cluster.name)
    assert crs, "no GroupSync CRs found — check the CRD is installed"
    for cr in crs:
        assert cr["namespace"], f"{cr['name']} has no namespace"
        assert is_valid_schedule(cr["schedule"]), f"{cr['name']} schedule {cr['schedule']!r}"


def test_groups_are_attributed_to_their_cr(polled):
    """PLAN §3: without the sync-provider label the dashboard is two unrelated lists."""
    store, cluster, _ = polled
    groups = store.groups(cluster.name, "all")
    assert groups, "no groups found"
    keys = {k for cr in store.groupsyncs(cluster.name) for k in cr["provider_keys"]}
    managed = [g for g in groups if g["sync_provider"]]
    assert managed, "no group carries a sync-provider label"
    assert {g["sync_provider"] for g in managed} <= keys


def test_every_sync_event_has_both_timestamps(polled):
    """observed_at - synced_at is OUR lag; conflating them would blame the operator."""
    store, cluster, _ = polled
    for cr in store.groupsyncs(cluster.name):
        for event in store.sync_events(cluster.name, cr["name"], None, 50):
            assert event["synced_at"] and event["observed_at"]
            assert event["schedule"], "schedule must be snapshotted onto the event"
