"""RBAC binding visibility and the three-tier finding classification.

The classification is the whole design risk. On the target cluster 110 of 149 distinct
Group subjects are built-in virtual groups, 9 name groups that have never existed, and 0
are groups that broke after being managed. A two-tier "does a Group object exist" check
reports 119 problems of which 9 matter — a list that is 92% noise is one operators stop
reading, so these tests pin the tiers apart.
"""

from __future__ import annotations

import pytest

from gsd.kube import BindingView, _binding_views
from gsd.store import Store

T1 = "2026-08-01T09:00:00Z"
T2 = "2026-08-01T09:05:00Z"


@pytest.fixture()
def store():
    s = Store(":memory:")
    s.upsert_cluster("crc", "https://x", True)
    yield s
    s.close()


def bind(group, kind="RoleBinding", ns="alpha-dev", name=None, role="edit",
         role_kind="ClusterRole"):
    return {
        "binding_kind": kind,
        "binding_namespace": ns if kind == "RoleBinding" else "",
        "binding_name": name or f"{group}-rb",
        "role_kind": role_kind,
        "role_name": role,
        "group_name": group,
    }


def group_row(name, provider="ldap-groupsync_ldap"):
    return {"name": name, "member_count": 1, "sync_provider": provider,
            "group_synced_at": T1, "ldap_uid": None}


class TestParsing:
    def test_only_group_subjects_are_kept(self):
        """User and ServiceAccount subjects cannot contribute to access-via-groups."""
        obj = {
            "metadata": {"name": "mixed-rb", "namespace": "alpha"},
            "roleRef": {"kind": "ClusterRole", "name": "edit"},
            "subjects": [
                {"kind": "Group", "name": "app-team"},
                {"kind": "User", "name": "alice"},
                {"kind": "ServiceAccount", "name": "builder", "namespace": "alpha"},
            ],
        }
        rows = _binding_views(obj, "RoleBinding")
        assert [r.group_name for r in rows] == ["app-team"]

    def test_a_binding_with_several_groups_becomes_several_rows(self):
        obj = {
            "metadata": {"name": "multi", "namespace": "alpha"},
            "roleRef": {"kind": "ClusterRole", "name": "view"},
            "subjects": [{"kind": "Group", "name": "a"}, {"kind": "Group", "name": "b"}],
        }
        assert sorted(r.group_name for r in _binding_views(obj, "RoleBinding")) == ["a", "b"]

    def test_clusterrolebinding_has_empty_namespace_not_none(self):
        """'' rather than None so it can sit in a NOT NULL primary key column."""
        obj = {"metadata": {"name": "crb"}, "roleRef": {"kind": "ClusterRole", "name": "admin"},
               "subjects": [{"kind": "Group", "name": "g"}]}
        assert _binding_views(obj, "ClusterRoleBinding")[0].binding_namespace == ""

    def test_binding_with_no_subjects_yields_nothing(self):
        obj = {"metadata": {"name": "empty"}, "roleRef": {"kind": "ClusterRole", "name": "view"}}
        assert _binding_views(obj, "RoleBinding") == []

    def test_system_group_is_recognised(self):
        assert BindingView("RoleBinding", "ns", "b", "ClusterRole", "r",
                           "system:serviceaccounts:ns").is_system_group
        assert not BindingView("RoleBinding", "ns", "b", "ClusterRole", "r",
                               "app-team").is_system_group


class TestFindingTiers:
    def test_bound_group_that_exists_is_not_a_finding(self, store):
        store.replace_group_state("crc", [group_row("app-team")], T1)
        store.replace_bindings("crc", [bind("app-team")], T1)
        assert store.binding_findings("crc") == []

    def test_system_group_is_built_in_not_broken(self, store):
        """110 of 149 real subjects look like this. They authorise real access and no
        Group object exists or ever will."""
        store.replace_group_state("crc", [], T1)
        store.replace_bindings("crc", [bind("system:serviceaccounts:beta-prod")], T1)
        finding = store.binding_findings("crc")[0]
        assert finding["finding"] == "built_in"

    def test_never_seen_group_is_unresolved_not_dangling(self, store):
        """The klt/klta/toolongx case: a binding naming a group that has never existed.
        Real, but we cannot prove it is a typo rather than something we do not know about,
        so it must not claim the confidence of `dangling`."""
        store.replace_group_state("crc", [], T1)
        store.replace_bindings("crc", [bind("app-ocp-rbac-toolongx-ns-developer")], T1)
        assert store.binding_findings("crc")[0]["finding"] == "unresolved"

    def test_formerly_managed_group_that_vanished_is_dangling(self, store):
        """The high-confidence tier: we watched the operator manage this group, and now it
        is gone while a binding still names it. That binding grants nobody."""
        store.replace_group_state("crc", [group_row("app-team")], T1)
        store.record_managed_groups("crc", [group_row("app-team")], T1)
        store.replace_bindings("crc", [bind("app-team")], T1)
        assert store.binding_findings("crc") == []

        store.replace_group_state("crc", [], T2)  # the group disappears
        finding = store.binding_findings("crc")[0]
        assert finding["finding"] == "dangling"
        assert finding["group_name"] == "app-team"

    def test_unmanaged_group_that_vanishes_is_not_promoted_to_dangling(self, store):
        """A group we never saw the operator manage has no provenance, so its absence is
        unresolved however long we have been running."""
        store.replace_group_state("crc", [group_row("manual-group", provider=None)], T1)
        store.record_managed_groups("crc", [group_row("manual-group", provider=None)], T1)
        store.replace_bindings("crc", [bind("manual-group")], T1)
        store.replace_group_state("crc", [], T2)
        assert store.binding_findings("crc")[0]["finding"] == "unresolved"

    def test_first_run_does_not_mass_report_dangling(self, store):
        """On a cold start nothing has provenance yet, so no binding may be called broken —
        otherwise every restart would alarm."""
        store.replace_group_state("crc", [], T1)
        store.replace_bindings(
            "crc", [bind("a"), bind("b"), bind("system:authenticated")], T1
        )
        tiers = {f["finding"] for f in store.binding_findings("crc")}
        assert "dangling" not in tiers

    def test_realistic_mix_isolates_the_signal(self, store):
        """The measured shape: mostly built-in, a few never-seen, one genuinely broken."""
        store.replace_group_state("crc", [group_row("live-group")], T1)
        store.record_managed_groups(
            "crc", [group_row("live-group"), group_row("was-managed")], T1
        )
        store.replace_bindings(
            "crc",
            [bind(f"system:serviceaccounts:ns{i}") for i in range(20)]
            + [bind("app-ocp-rbac-klt-ns-admin"), bind("app-ocp-rbac-klta-ns-audit")]
            + [bind("live-group"), bind("was-managed")],
            T1,
        )
        tiers: dict[str, int] = {}
        for f in store.binding_findings("crc"):
            tiers[f["finding"]] = tiers.get(f["finding"], 0) + 1
        assert tiers == {"built_in": 20, "unresolved": 2, "dangling": 1}


class TestLookups:
    def test_group_bindings_lists_namespaces_and_cluster_scope(self, store):
        store.replace_bindings(
            "crc",
            [
                bind("app-team", ns="alpha-dev", role="edit"),
                bind("app-team", ns="beta-prod", role="view", name="app-team-view"),
                bind("app-team", kind="ClusterRoleBinding", role="cluster-reader"),
            ],
            T1,
        )
        rows = store.group_bindings("crc", "app-team")
        assert len(rows) == 3
        ns = {r["binding_namespace"] for r in rows if r["binding_kind"] == "RoleBinding"}
        assert ns == {"alpha-dev", "beta-prod"}
        crb = [r for r in rows if r["binding_kind"] == "ClusterRoleBinding"]
        assert crb[0]["binding_namespace"] == "" and crb[0]["role_name"] == "cluster-reader"

    def test_user_bindings_go_through_group_membership_and_carry_via_group(self, store):
        """Without via_group the page asserts access with no way to see what confers it —
        the first thing anyone asks when revoking it."""
        store.sync_members("crc", {"app-team": ["alice"], "ops": ["alice"]}, {}, T1)
        store.replace_bindings(
            "crc", [bind("app-team", ns="alpha-dev"), bind("ops", ns="ops-ns", role="admin")], T1
        )
        rows = store.user_bindings("crc", "alice")
        assert {(r["binding_namespace"], r["role_name"], r["via_group"]) for r in rows} == {
            ("alpha-dev", "edit", "app-team"),
            ("ops-ns", "admin", "ops"),
        }

    def test_user_loses_bindings_when_they_leave_the_group(self, store):
        store.sync_members("crc", {"app-team": ["alice"]}, {}, T1)
        store.replace_bindings("crc", [bind("app-team")], T1)
        assert len(store.user_bindings("crc", "alice")) == 1
        store.sync_members("crc", {"app-team": []}, {}, T2)
        assert store.user_bindings("crc", "alice") == []

    def test_bindings_are_replaced_not_accumulated(self, store):
        store.replace_bindings("crc", [bind("a"), bind("b")], T1)
        store.replace_bindings("crc", [bind("a")], T2)
        assert [r["role_name"] for r in store.group_bindings("crc", "b")] == []

    def test_clusters_are_isolated(self, store):
        store.upsert_cluster("c2", "https://y", True)
        store.replace_bindings("crc", [bind("g", ns="a")], T1)
        store.replace_bindings("c2", [bind("g", ns="b")], T1)
        assert store.group_bindings("crc", "g")[0]["binding_namespace"] == "a"
        assert store.group_bindings("c2", "g")[0]["binding_namespace"] == "b"


class TestAdversarialFindings:
    """Defects found by an adversarial review (Grok 4.5), reproduced before fixing."""

    def test_managed_group_with_system_prefix_still_reports_dangling(self, store):
        """The CASE tested `system:%` BEFORE provenance, so a group we had watched the
        operator manage was downgraded to `built_in` when it vanished — a binding granting
        nobody, with no alert. Evidence must outrank a naming heuristic.
        """
        g = group_row("system:ldap-admins")
        store.replace_group_state("crc", [g], T1)
        store.record_managed_groups("crc", [g], T1)
        store.replace_bindings("crc", [bind("system:ldap-admins")], T1)
        store.replace_group_state("crc", [], T2)
        assert store.binding_findings("crc")[0]["finding"] == "dangling"

    def test_genuine_virtual_group_is_still_built_in(self, store):
        """The fix must not swing the other way: a real virtual group has no provenance and
        must stay out of the alerting tier."""
        store.replace_group_state("crc", [], T1)
        store.replace_bindings("crc", [bind("system:authenticated")], T1)
        assert store.binding_findings("crc")[0]["finding"] == "built_in"
