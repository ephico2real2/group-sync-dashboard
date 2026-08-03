"""Tests for the store's accumulation guarantees and the poller's attribution logic."""

import pytest

from gsd.kube import GroupSyncView, GroupView
from gsd.poller import provider_keys_for
from gsd.store import Store


@pytest.fixture()
def store():
    s = Store(":memory:")
    s.upsert_cluster("crc", "https://api.crc.testing:6443", True)
    yield s
    s.close()


class TestSyncEventAccumulation:
    def test_reobserving_the_same_sync_is_a_noop(self, store):
        """PLAN §10: the UNIQUE constraint makes polling faster than the schedule free.

        Without this, a 60s poll against a 30-minute schedule would write 30 identical
        rows per real sync and the 'timeline' would be a poll log.
        """
        args = ("crc", "ldap-groupsync", "group-sync-operator", "2026-08-01T07:00:10Z")
        assert store.record_sync_event(*args, "2026-08-01T07:00:30Z", "*/30 * * * *", 41) is True
        assert store.record_sync_event(*args, "2026-08-01T07:01:30Z", "*/30 * * * *", 41) is False
        assert len(store.sync_events("crc", "ldap-groupsync", None, 100)) == 1

    def test_a_new_timestamp_appends_an_event(self, store):
        for ts, count in [("2026-08-01T07:00:10Z", 40), ("2026-08-01T07:30:07Z", 41)]:
            store.record_sync_event(
                "crc", "ldap-groupsync", "group-sync-operator", ts, ts, "*/30 * * * *", count
            )
        events = store.sync_events("crc", "ldap-groupsync", None, 100)
        assert [e["group_count"] for e in events] == [41, 40]  # newest first

    def test_schedule_is_snapshotted_per_event(self, store):
        """PLAN §10: schedules change; old rows must stay interpretable against the
        schedule that was in force when they happened, not today's."""
        store.record_sync_event(
            "crc", "cr", "ns", "2026-07-31T16:00:00Z", "2026-07-31T16:00:30Z", "*/2 * * * *", 37
        )
        store.record_sync_event(
            "crc", "cr", "ns", "2026-08-01T07:00:00Z", "2026-08-01T07:00:30Z", "*/30 * * * *", 41
        )
        schedules = [e["schedule"] for e in store.sync_events("crc", "cr", None, 100)]
        assert schedules == ["*/30 * * * *", "*/2 * * * *"]

    def test_since_filters_the_timeline(self, store):
        for ts in ("2026-08-01T06:00:00Z", "2026-08-01T07:00:00Z"):
            store.record_sync_event("crc", "cr", "ns", ts, ts, "0 * * * *", 20)
        assert len(store.sync_events("crc", "cr", "2026-08-01T06:30:00Z", 100)) == 1


class TestGroupState:
    def test_replace_removes_groups_that_disappeared(self, store):
        """An upsert would leave deleted groups behind forever and inflate every count."""
        store.replace_group_state(
            "crc",
            [
                {"name": "a", "member_count": 1, "sync_provider": "cr_ldap",
                 "group_synced_at": None, "ldap_uid": None},
                {"name": "b", "member_count": 2, "sync_provider": "cr_ldap",
                 "group_synced_at": None, "ldap_uid": None},
            ],
            "2026-08-01T07:00:00Z",
        )
        store.replace_group_state(
            "crc",
            [{"name": "a", "member_count": 1, "sync_provider": "cr_ldap",
              "group_synced_at": None, "ldap_uid": None}],
            "2026-08-01T07:01:00Z",
        )
        assert [g["name"] for g in store.groups("crc")] == ["a"]

    def test_state_filters(self, store):
        store.replace_group_state(
            "crc",
            [
                {"name": "full", "member_count": 3, "sync_provider": "cr_ldap",
                 "group_synced_at": None, "ldap_uid": None},
                {"name": "empty", "member_count": 0, "sync_provider": "cr_ldap",
                 "group_synced_at": None, "ldap_uid": None},
                {"name": "orphan", "member_count": 1, "sync_provider": None,
                 "group_synced_at": None, "ldap_uid": None},
            ],
            "2026-08-01T07:00:00Z",
        )
        assert [g["name"] for g in store.groups("crc", "empty")] == ["empty"]
        assert [g["name"] for g in store.groups("crc", "unattributed")] == ["orphan"]
        assert store.group_counts("crc") == {"total": 3, "empty": 1, "unattributed": 1}

    def test_empty_includes_unmanaged_groups_and_overlaps_unattributed(self, store):
        """EMPTY is 'zero members', whatever created the group — and it OVERLAPS unattributed.

        This asserted the opposite while `empty` required `sync_provider IS NOT NULL`, on
        PLAN §7's reading of EMPTY as "synced, then lost its members". That made the filter
        useless on a cluster with no group-sync-operator: every group is unattributed there, so
        `empty` matched nothing however many groups granted nobody. Rescoped deliberately.

        The overlap is the contract now, so the thing to protect is that nobody ADDS the two
        counts together to describe a cluster.
        """
        store.replace_group_state(
            "crc",
            [{"name": "handmade", "member_count": 0, "sync_provider": None,
              "group_synced_at": None, "ldap_uid": None}],
            "2026-08-01T07:00:00Z",
        )
        assert [g["name"] for g in store.groups("crc", "empty")] == ["handmade"]
        assert [g["name"] for g in store.groups("crc", "unattributed")] == ["handmade"]
        assert store.group_counts("crc") == {"total": 1, "empty": 1, "unattributed": 1}

    def test_unknown_filter_is_rejected(self, store):
        """A typo'd filter must not silently fall through to 'all' and misreport."""
        with pytest.raises(ValueError):
            store.groups("crc", "emtpy")


class TestReconcileError:
    def test_upsert_then_clear(self, store):
        store.upsert_reconcile_error("crc", "cr", "2026-07-30T15:16:17Z", 1, "kyverno down")
        assert store.groupsyncs("crc") == []  # no CR state rows yet
        store.replace_groupsync_state(
            "crc",
            [{"name": "cr", "namespace": "ns", "schedule": "0 * * * *", "ldap_filter": None,
              "last_sync_at": "2026-08-01T07:00:10Z", "generation": 2, "provider_keys": ["cr_ldap"]}],
            "2026-08-01T07:00:30Z",
        )
        row = store.groupsyncs("crc")[0]
        assert row["error_at"] == "2026-07-30T15:16:17Z"
        assert row["error_message"] == "kyverno down"

        store.upsert_reconcile_error("crc", "cr", None, None, None)
        assert store.groupsyncs("crc")[0]["error_at"] is None


class TestMultiProviderAttribution:
    """A CR declaring several providers, end to end through the store."""

    def _write(self, store, provider_keys, groups):
        store.replace_groupsync_state(
            "crc",
            [{"name": "corp", "namespace": "ns", "schedule": "0 * * * *", "ldap_filter": None,
              "last_sync_at": "2026-08-01T07:00:10Z", "generation": 1,
              "provider_keys": provider_keys}],
            "2026-08-01T07:00:30Z",
        )
        store.replace_group_state(
            "crc",
            [{"name": n, "member_count": 1, "sync_provider": p,
              "group_synced_at": None, "ldap_uid": None} for n, p in groups],
            "2026-08-01T07:00:30Z",
        )

    def test_all_keys_round_trip(self, store):
        self._write(store, ["corp_ldap-a", "corp_ldap-b"], [])
        assert store.groupsyncs("crc")[0]["provider_keys"] == ["corp_ldap-a", "corp_ldap-b"]

    def test_group_count_spans_every_provider(self, store):
        """The count on the CR card. Keeping only the first key undercounted it by every
        group the later providers produced, which reads as 'the sync shrank'."""
        self._write(
            store,
            ["corp_ldap-a", "corp_ldap-b"],
            [("g1", "corp_ldap-a"), ("g2", "corp_ldap-b"), ("g3", "corp_ldap-b"),
             ("other", "unrelated_ldap")],
        )
        assert store.groupsyncs("crc")[0]["group_count"] == 3

    def test_providers_are_replaced_not_accumulated(self, store):
        """Same delete-then-insert contract as the CR state itself: a provider removed from
        the CR must stop owning groups, or its stale attribution outlives it forever."""
        self._write(store, ["corp_ldap-a", "corp_ldap-b"], [])
        self._write(store, ["corp_ldap-a"], [])
        assert store.groupsyncs("crc")[0]["provider_keys"] == ["corp_ldap-a"]

    def test_cr_with_no_providers_yet_has_an_empty_list(self, store):
        """Never None: every caller treats this as a list to test membership against."""
        self._write(store, [], [("g1", "corp_ldap-a")])
        row = store.groupsyncs("crc")[0]
        assert row["provider_keys"] == [] and row["group_count"] == 0

    def test_a_second_cluster_does_not_inherit_the_attributions(self, store):
        """cluster_id is in the key, but the DELETE is per-cluster and the subquery joins on
        it — a leak here would silently give one cluster's groups another cluster's owner."""
        store.upsert_cluster("other", "https://api.other:6443", True)
        self._write(store, ["corp_ldap-a"], [("g1", "corp_ldap-a")])
        assert store.groupsyncs("other") == []
        assert store.groupsyncs("crc")[0]["provider_keys"] == ["corp_ldap-a"]


class TestPollOutcome:
    def test_forbidden_is_distinguishable_from_unreachable(self, store):
        """PLAN §12 step 7: a SA that can list GroupSync but not Group otherwise looks
        exactly like a cluster with no groups."""
        store.record_poll("crc", "forbidden", "403 on /groups")
        row = store.clusters()[0]
        assert row["status"] == "forbidden" and "403" in row["message"]
        store.record_poll("crc", "unreachable", "connect timeout")
        assert store.clusters()[0]["status"] == "unreachable"

    def test_never_polled_cluster_has_null_status(self, store):
        assert store.clusters()[0]["status"] is None


class TestProviderAttribution:
    def _cr(self, name):
        return GroupSyncView(name, "ns", "0 * * * *", None, None, 1, None, None, None, None)

    def _group(self, name, provider):
        return GroupView(name, 1, provider, None, None, ["alice"])

    def test_matches_the_label_actually_present(self, store):
        """The provider suffix is not on the CR status, so it is discovered from the
        Groups rather than reconstructed and hoped for."""
        groups = [self._group("g1", "ldap-groupsync_ldap"), self._group("g2", "bda-rbac-groupsync_ldap")]
        assert provider_keys_for(self._cr("ldap-groupsync"), groups) == ["ldap-groupsync_ldap"]
        assert provider_keys_for(self._cr("bda-rbac-groupsync"), groups) == ["bda-rbac-groupsync_ldap"]

    def test_cr_with_no_groups_yet_returns_empty(self):
        """Empty, not [''], so it cannot accidentally match every unlabelled group."""
        assert provider_keys_for(self._cr("brand-new"), [self._group("g", "other_ldap")]) == []

    def test_prefix_match_is_anchored(self):
        """`ldap-groupsync` must not claim `ldap-groupsync-staging_ldap`'s groups."""
        groups = [self._group("g", "ldap-groupsync-staging_ldap")]
        assert provider_keys_for(self._cr("ldap-groupsync"), groups) == []

    def test_every_provider_of_a_multi_provider_cr_is_claimed(self):
        """A CR declaring several providers produces one label value per provider. Taking
        only the first left the rest with no owner, and an unowned group is never
        staleness-checked — it just disappears from every overdue calculation."""
        groups = [
            self._group("g1", "corp_ldap-a"),
            self._group("g2", "corp_ldap-b"),
            self._group("g3", "corp_ldap-a"),
            self._group("g4", "other_ldap"),
        ]
        assert provider_keys_for(self._cr("corp"), groups) == ["corp_ldap-a", "corp_ldap-b"]

    def test_keys_are_sorted_so_attribution_is_stable(self):
        """The Group list arrives in whatever order the API returns it. Attribution must
        not change between polls just because that order did."""
        forward = [self._group("g1", "corp_a"), self._group("g2", "corp_b")]
        assert provider_keys_for(self._cr("corp"), forward) == provider_keys_for(
            self._cr("corp"), list(reversed(forward))
        )


class TestAttributionAmbiguity:
    """Codex M1: prefix matching produced reachable cross-CR attribution.

    The operator labels each Group `<groupsync-name>_<provider-name>`. Matching purely on
    the `<name>_` prefix means a CR whose name is a prefix of another CR's name claims the
    other's groups too — so one group gets two owners, is counted in both CRs' group_count,
    and raises two stale alerts for one problem.
    """

    def _cr(self, name, namespace="ns", providers=("ldap",)):
        return GroupSyncView(name, namespace, "0 * * * *", None, None, 1,
                             None, None, None, None, tuple(providers))

    def _group(self, name, provider):
        return GroupView(name, 1, provider, None, None, ["alice"])

    def test_a_prefix_named_cr_no_longer_steals_another_cr_s_group(self):
        """`corp` and `corp_extra` both matched `corp_extra_ldap` before this."""
        groups = [self._group("g", "corp_extra_ldap")]
        assert provider_keys_for(self._cr("corp"), groups) == []
        assert provider_keys_for(self._cr("corp_extra"), groups) == ["corp_extra_ldap"]

    def test_declared_names_are_matched_exactly_not_by_prefix(self):
        """A label whose suffix is not a declared provider belongs to nobody here."""
        groups = [self._group("g", "corp_somethingelse")]
        assert provider_keys_for(self._cr("corp", providers=("ldap",)), groups) == []

    def test_a_multi_provider_cr_still_claims_all_of_its_own(self):
        groups = [self._group("a", "corp_ldap-a"), self._group("b", "corp_ldap-b"),
                  self._group("c", "other_ldap")]
        keys = provider_keys_for(self._cr("corp", providers=("ldap-a", "ldap-b")), groups)
        assert keys == ["corp_ldap-a", "corp_ldap-b"]

    def test_a_spec_without_provider_names_falls_back_to_prefix(self):
        """Older or hand-written CRs may omit names; attribution must not simply stop."""
        groups = [self._group("g", "corp_ldap")]
        assert provider_keys_for(self._cr("corp", providers=()), groups) == ["corp_ldap"]

    def test_same_name_in_two_namespaces_is_reported_not_guessed(self):
        """The label carries no namespace, so this is genuinely undecidable from the data.
        Saying so beats attributing to whichever CR happened to be iterated first."""
        from gsd.poller import ambiguous_attribution
        crs = [self._cr("team", "ns-a"), self._cr("team", "ns-b"), self._cr("other", "ns-a")]
        assert ambiguous_attribution(crs) == ["team"]

    def test_no_ambiguity_reported_for_distinct_names(self):
        from gsd.poller import ambiguous_attribution
        assert ambiguous_attribution([self._cr("a"), self._cr("b")]) == []
