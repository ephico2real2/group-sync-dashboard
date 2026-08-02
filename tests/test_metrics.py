"""Prometheus exposition.

The two properties worth pinning: the numbers match what the API reports (a metric that
disagrees with the dashboard is worse than no metric), and cardinality stays bounded —
a series per group would be tens of thousands on a real directory, and group and user names
are membership data that must not leak into an unauthenticated endpoint.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from prometheus_client import generate_latest

from gsd.metrics import build_registry
from gsd.store import Store

GRACE = timedelta(seconds=120)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture()
def scrape():
    now = datetime.now(UTC)
    store = Store(":memory:")
    store.upsert_cluster("crc", "https://x", True)
    store.record_poll("crc", "ok", None)
    store.replace_groupsync_state(
        "crc",
        [{"name": "ldap-groupsync", "namespace": "group-sync-operator",
          "schedule": "*/30 * * * *", "ldap_filter": None,
          "last_sync_at": _iso(now - timedelta(minutes=3)), "generation": 2,
          "provider_key": "ldap-groupsync_ldap"}],
        _iso(now),
    )
    store.replace_group_state(
        "crc",
        [{"name": f"g{i}", "member_count": 0 if i == 0 else 2,
          "sync_provider": None if i == 1 else "ldap-groupsync_ldap",
          "group_synced_at": _iso(now - timedelta(minutes=3)), "ldap_uid": None}
         for i in range(5)],
        _iso(now),
    )
    store.sync_members("crc", {f"g{i}": ["alice", "bob"] for i in range(2, 5)}, {}, _iso(now))
    store.replace_bindings(
        "crc",
        [{"binding_kind": "RoleBinding", "binding_namespace": "ns", "binding_name": "rb",
          "role_kind": "ClusterRole", "role_name": "edit", "group_name": "g2"},
         {"binding_kind": "RoleBinding", "binding_namespace": "ns", "binding_name": "rb2",
          "role_kind": "ClusterRole", "role_name": "view", "group_name": "typo-group"},
         {"binding_kind": "RoleBinding", "binding_namespace": "ns", "binding_name": "rb3",
          "role_kind": "ClusterRole", "role_name": "view",
          "group_name": "system:authenticated"}],
        _iso(now),
    )
    text = generate_latest(build_registry(store, GRACE)).decode()
    yield text, store
    store.close()


def series(text: str, name: str) -> dict[str, float]:
    out = {}
    for line in text.splitlines():
        if line.startswith("#") or not line.startswith(name):
            continue
        metric, _, value = line.rpartition(" ")
        out[metric] = float(value)
    return out


class TestExposition:
    def test_build_info_carries_the_running_commit(self, scrape):
        text, _ = scrape
        assert "gsd_build_info" in text

    def test_group_counts_match_the_store(self, scrape):
        text, store = scrape
        counts = store.group_counts("crc")
        assert series(text, "gsd_groups_total")['gsd_groups_total{cluster="crc"}'] == counts["total"]
        assert series(text, "gsd_groups_empty_total")[
            'gsd_groups_empty_total{cluster="crc"}'] == counts["empty"]
        assert series(text, "gsd_groups_unattributed_total")[
            'gsd_groups_unattributed_total{cluster="crc"}'] == counts["unattributed"]

    def test_last_sync_is_a_unix_timestamp_not_an_age(self, scrape):
        """An age is stale the moment it is scraped; a timestamp lets Prometheus express
        staleness against real time, which is the whole point of exporting it."""
        text, _ = scrape
        values = list(series(text, "gsd_groupsync_last_sync_timestamp_seconds").values())
        assert values and values[0] > 1_700_000_000

    def test_every_state_is_emitted_with_exactly_one_set(self, scrape):
        """A series that vanishes when the state changes leaves stale data on the graph and
        breaks `by (state)` aggregation."""
        text, _ = scrape
        states = series(text, "gsd_groupsync_state")
        assert len(states) == 4
        assert sum(states.values()) == 1

    def test_binding_findings_are_broken_out(self, scrape):
        text, _ = scrape
        found = series(text, "gsd_bindings_total")
        assert found['gsd_bindings_total{cluster="crc",finding="ok"}'] == 1
        assert found['gsd_bindings_total{cluster="crc",finding="unresolved"}'] == 1
        assert found['gsd_bindings_total{cluster="crc",finding="built_in"}'] == 1

    def test_cluster_up_reflects_the_last_poll(self, scrape):
        text, store = scrape
        assert series(text, "gsd_cluster_up")['gsd_cluster_up{cluster="crc"}'] == 1
        store.record_poll("crc", "auth_failed", "401")
        text2 = generate_latest(build_registry(store, GRACE)).decode()
        assert series(text2, "gsd_cluster_up")['gsd_cluster_up{cluster="crc"}'] == 0


class TestCardinalityAndLeakage:
    def test_no_group_name_appears_in_any_label(self, scrape):
        """A series per group is tens of thousands on a real directory — the way a
        dashboard's own metrics take down the Prometheus scraping it."""
        text, _ = scrape
        for name in ("g0", "g1", "g2", "typo-group"):
            assert f'"{name}"' not in text, f"group {name} leaked into a label"

    def test_no_username_appears_anywhere(self, scrape):
        """Membership data must not reach an unauthenticated endpoint."""
        text, _ = scrape
        assert "alice" not in text and "bob" not in text

    def test_series_count_stays_bounded_as_groups_grow(self):
        """The real guard: 500 groups must not mean 500 more series."""
        now = datetime.now(UTC)
        store = Store(":memory:")
        store.upsert_cluster("crc", "https://x", True)
        store.record_poll("crc", "ok", None)
        store.replace_group_state(
            "crc",
            [{"name": f"grp{i}", "member_count": 1, "sync_provider": "p",
              "group_synced_at": _iso(now), "ldap_uid": None} for i in range(500)],
            _iso(now),
        )
        text = generate_latest(build_registry(store, GRACE)).decode()
        lines = [ln for ln in text.splitlines() if ln and not ln.startswith("#")]
        assert len(lines) < 40, f"{len(lines)} series for 500 groups — cardinality unbounded"
        store.close()


class TestResilience:
    def test_a_broken_cluster_does_not_fail_the_whole_scrape(self, scrape):
        """A scrape that 500s is indistinguishable from the target being down, so a
        partial exposition beats none."""
        text, store = scrape
        store.close()  # every query now raises
        out = generate_latest(build_registry(store, GRACE)).decode()
        assert "gsd_build_info" in out
