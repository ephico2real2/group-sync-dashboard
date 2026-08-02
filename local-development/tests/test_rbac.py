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


class TestUnmanagedFinding:
    """A hand-made grant on an operator-synced group, outside the policy system.

    Live motivation: on the reference cluster 77 of 85 convention bindings carry the
    policy operator's `rbac.ocp.io/config-source` label, and the handful that do not are
    exactly the hand-made ones — including a ClusterRoleBinding granting cluster-admin
    that nothing manages. The finding makes that class visible; the exception annotation
    lets a deliberate one be acknowledged ON the binding, so the justification lives next
    to the object instead of in a dashboard-side allowlist.
    """

    def _seed(self, store, bindings):
        store.replace_group_state(
            "crc",
            [{"name": "app-ocp-rbac-team-ns-admin", "member_count": 1,
              "sync_provider": "ldap-groupsync_ldap", "group_synced_at": None,
              "ldap_uid": None}],
            "2026-08-02T18:00:00Z",
        )
        store.record_managed_groups(
            "crc", [{"name": "app-ocp-rbac-team-ns-admin",
                     "sync_provider": "ldap-groupsync_ldap"}],
            "2026-08-02T18:00:00Z",
        )
        store.replace_bindings("crc", bindings, "2026-08-02T18:00:00Z")

    def _binding(self, name, **kw):
        return {"binding_kind": "RoleBinding", "binding_namespace": "ns-a",
                "binding_name": name, "role_kind": "ClusterRole", "role_name": "admin",
                "group_name": "app-ocp-rbac-team-ns-admin",
                "managed_source": None, "exception": None, **kw}

    def test_a_hand_made_grant_on_a_managed_group_is_flagged(self, store):
        self._seed(store, [
            self._binding("managed", managed_source="prod-rbac"),
            self._binding("hand-made"),
        ])
        findings = {r["binding_name"]: r["finding"] for r in store.all_bindings("crc")}
        assert findings["managed"] == "ok"
        assert findings["hand-made"] == "unmanaged"

    def test_the_exception_annotation_acknowledges_it(self, store):
        """The justification travels on the binding itself; the finding clears."""
        self._seed(store, [
            self._binding("managed", managed_source="prod-rbac"),
            self._binding("deliberate", exception="test scaffolding — JIRA-123"),
        ])
        findings = {r["binding_name"]: r["finding"] for r in store.all_bindings("crc")}
        assert findings["deliberate"] == "ok"

    def test_silent_on_a_cluster_that_does_not_use_the_policy_operator(self, store):
        """No binding anywhere carries a config-source label -> the concept does not
        exist on this cluster, and flagging every binding would be 100% noise."""
        self._seed(store, [self._binding("hand-made")])
        findings = {r["binding_name"]: r["finding"] for r in store.all_bindings("crc")}
        assert findings["hand-made"] == "ok"

    def test_broken_resolution_outranks_provenance(self, store):
        """A binding that grants NOBODY is worse than one that grants outside governance;
        it must not be downgraded to `unmanaged` just because it is also unlabelled."""
        store.record_managed_groups(
            "crc", [{"name": "was-managed", "sync_provider": "ldap-groupsync_ldap"}],
            "2026-08-01T00:00:00Z",
        )
        store.replace_bindings("crc", [
            self._binding("managed-elsewhere", managed_source="prod-rbac"),
            self._binding("grants-nobody", group_name="was-managed"),
        ], "2026-08-02T18:00:00Z")
        findings = {r["binding_name"]: r["finding"] for r in store.all_bindings("crc")}
        assert findings["grants-nobody"] == "dangling"


class TestOperatorConfigAlerts:
    def test_a_current_config_error_alerts(self, store):
        from datetime import UTC, datetime, timedelta as td
        import gsd.state as st
        alerts = st.compute_alerts(
            "crc", [], [], datetime.now(UTC), td(minutes=2),
            operator_configs=[{"kind": "NamespaceConfig", "name": "multitenant",
                               "error_at": "2026-08-02T18:00:00Z",
                               "error_message": "webhook refused",
                               "success_at": "2026-08-02T17:00:00Z"}],
        )
        assert [a.kind for a in alerts] == ["config_reconcile_error"]
        assert alerts[0].subject == "NamespaceConfig/multitenant"

    def test_a_superseded_error_stays_quiet(self, store):
        """The operator never clears ReconcileError — both conditions sit True forever —
        so only the transition-time ordering decides. Same trap as GroupSync, verified
        live: `multitenant` carried a day-old error under a fresh success."""
        from datetime import UTC, datetime, timedelta as td
        import gsd.state as st
        alerts = st.compute_alerts(
            "crc", [], [], datetime.now(UTC), td(minutes=2),
            operator_configs=[{"kind": "NamespaceConfig", "name": "multitenant",
                               "error_at": "2026-08-01T22:22:17Z",
                               "error_message": "net/http: request canceled",
                               "success_at": "2026-08-02T17:58:23Z"}],
        )
        assert alerts == []


class TestDirectUserGrants:
    """Namespace audit: roles bound to a PERSON rather than an LDAP-managed group.

    The violation survives offboarding — removing someone from an LDAP group revokes their
    access everywhere at once, while a binding that names them keeps granting to a name
    nobody reviews — and no group-based audit, including the rest of this dashboard, can
    see it.
    """

    def _seed(self, store, rows):
        store.replace_user_bindings("crc", rows, "2026-08-02T20:00:00Z")

    def _u(self, ns, name, user, role="edit", platform=0, kind="RoleBinding"):
        return {"binding_kind": kind, "binding_namespace": ns, "binding_name": name,
                "role_kind": "ClusterRole", "role_name": role, "user_name": user,
                "is_platform": platform}

    def test_platform_identities_are_excluded_by_default(self, store):
        """22 of 36 direct-user bindings on the reference cluster are system components.
        Including them would make the finding a platform-noise report."""
        self._seed(store, [self._u("ns-a", "real", "jdoe"),
                           self._u("", "sys", "system:admin", platform=1,
                                   kind="ClusterRoleBinding")])
        assert [r["user_name"] for r in store.direct_user_bindings("crc")] == ["jdoe"]
        assert store.platform_user_binding_count("crc") == 1

    def test_excluded_rows_are_counted_not_silently_dropped(self, store):
        """A tool that quietly discards rows cannot be trusted about the ones it keeps."""
        self._seed(store, [self._u("", "s", "system:x", platform=1,
                                   kind="ClusterRoleBinding")])
        assert store.direct_user_bindings("crc") == []
        assert store.platform_user_binding_count("crc") == 1
        assert len(store.direct_user_bindings("crc", include_platform=True)) == 1

    def test_the_rollup_is_per_namespace_worst_first(self, store):
        self._seed(store, [
            self._u("quiet-ns", "one", "jdoe"),
            self._u("busy-ns", "a", "jdoe"), self._u("busy-ns", "b", "asmith"),
            self._u("busy-ns", "c", "bwilliams"),
        ])
        rollup = store.user_bindings_by_namespace("crc")
        assert [r["namespace"] for r in rollup] == ["busy-ns", "quiet-ns"]
        assert rollup[0]["bindings"] == 3 and rollup[0]["distinct_users"] == 3

    def test_distinct_users_differs_from_binding_count(self, store):
        """One person with three bindings is one offboarding risk; three people is three."""
        self._seed(store, [self._u("ns-a", f"b{i}", "jdoe") for i in range(3)])
        row = store.user_bindings_by_namespace("crc")[0]
        assert row["bindings"] == 3 and row["distinct_users"] == 1

    def test_cluster_scoped_bindings_are_labelled_not_blank(self, store):
        self._seed(store, [self._u("", "crb", "jdoe", kind="ClusterRoleBinding")])
        assert store.user_bindings_by_namespace("crc")[0]["namespace"] == "(cluster-scoped)"

    def test_the_worklist_is_ordered_by_privilege(self, store):
        """cluster-admin first, then cluster-scoped, then namespaced: migration order."""
        self._seed(store, [
            self._u("ns-a", "low", "jdoe", role="view"),
            self._u("", "worst", "jdoe", role="cluster-admin", kind="ClusterRoleBinding"),
        ])
        assert [r["role_name"] for r in store.direct_user_bindings("crc")] == [
            "cluster-admin", "view"]


class TestDirectUserAlert:
    def test_one_alert_summarises_all_of_them(self, store):
        """One alert, not one per binding: 36 separate alerts would drown every other
        finding, and the actionable unit is the migration, not each row."""
        from datetime import UTC, datetime, timedelta as td
        import gsd.state as st
        alerts = st.compute_alerts(
            "crc", [], [], datetime.now(UTC), td(minutes=2),
            user_bindings=[
                {"binding_namespace": "ns-a", "role_name": "admin", "is_platform": 0},
                {"binding_namespace": "ns-b", "role_name": "view", "is_platform": 0},
            ],
        )
        assert [a.kind for a in alerts] == ["direct_user_binding"]
        assert "2 direct user grants" in alerts[0].subject
        assert "2 namespaces" in alerts[0].detail

    def test_platform_only_raises_nothing(self, store):
        from datetime import UTC, datetime, timedelta as td
        import gsd.state as st
        assert st.compute_alerts(
            "crc", [], [], datetime.now(UTC), td(minutes=2),
            user_bindings=[{"binding_namespace": "", "role_name": "x", "is_platform": 1}],
        ) == []
