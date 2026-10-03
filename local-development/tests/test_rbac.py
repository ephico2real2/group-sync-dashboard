"""RBAC binding visibility and the three-tier finding classification.

The classification is the whole design risk. On the target cluster 110 of 149 distinct
Group subjects are built-in virtual groups, 9 name groups that have never existed, and 0
are groups that broke after being managed. A two-tier "does a Group object exist" check
reports 119 problems of which 9 matter — a list that is 92% noise is one operators stop
reading, so these tests pin the tiers apart.
"""

from __future__ import annotations

import pytest

from gsd.kube import CHART_CONFIG_SOURCE, SUBJECT_KINDS, BindingView, _binding_views
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
    def test_every_subject_kind_is_kept_with_its_kind(self):
        """#353: a hand-made grant is a finding whoever it names, so User and ServiceAccount
        subjects are rows too, each saying what it is; the Group-only questions filter in the store."""
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
        assert [(r.subject_kind, r.subject_namespace, r.group_name) for r in rows] == [
            ("Group", "", "app-team"), ("User", "", "alice"), ("ServiceAccount", "alpha", "builder")]
        assert set(SUBJECT_KINDS) == {"Group", "User", "ServiceAccount"}

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

    def test_the_charts_own_label_does_not_mean_a_policy_operator_is_in_use(self, store):
        """#312: the chart labels its own auditor binding, and that binding is on every host by
        default. It must stay unreported without switching the finding on for a cluster no policy
        operator governs; only a policy operator's label does that."""
        chart = self._binding("chart-auditor", managed_source=CHART_CONFIG_SOURCE)
        self._seed(store, [chart, self._binding("hand-made")])
        findings = {r["binding_name"]: r["finding"] for r in store.all_bindings("crc")}
        assert findings == {"chart-auditor": "ok", "hand-made": "ok"}
        assert store.count_bindings_by_finding("crc").get("unmanaged", 0) == 0

        self._seed(store, [chart, self._binding("managed", managed_source="prod-rbac"),
                           self._binding("hand-made")])
        findings = {r["binding_name"]: r["finding"] for r in store.all_bindings("crc")}
        assert findings == {"chart-auditor": "ok", "managed": "ok", "hand-made": "unmanaged"}

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

    def test_the_user_list_is_a_list_not_a_delimited_string(self, store):
        """A user name can be an LDAP DN, which contains commas.

        The rollup used to GROUP_CONCAT this, and the page counted distinct people by
        splitting on a comma — so one `cn=jdoe,ou=people,dc=example,dc=com` became four
        people. store.py already states the rule for `provider_keys`: building a list by
        splitting a delimited string means picking a delimiter the value can never contain.
        """
        dn = "cn=jdoe,ou=people,dc=example,dc=com"
        self._seed(store, [self._u("ns-dn", "rb", dn)])
        row = store.user_bindings_by_namespace("crc")[0]
        assert row["users"] == [dn]
        assert row["distinct_users"] == len(row["users"]) == 1

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


class TestAcknowledgedDirectGrants:
    """#503: a direct user grant whose binding carries the operator's `rbac.ocp.io/config-source` label (any
    value) or the `rbac.ocp.io/unmanaged-exception` annotation is acknowledged. It leaves the worklist, its
    total, its rollup and the alert — the unmanaged finding's own rule (#353) — and is counted and listed
    instead, never dropped. The rows go through the real reader and a real binding refresh, so the provenance
    the view reads is the one the refresh stored."""

    @staticmethod
    def _crb(name, user, role="edit", labels=None, annotations=None):
        return {"metadata": {"name": name, "labels": labels or {}, "annotations": annotations or {}},
                "roleRef": {"kind": "ClusterRole", "name": role}, "subjects": [{"kind": "User", "name": user}]}

    def _refresh(self, store, monkeypatch, objects, user_list_only=()):
        """One binding refresh over ClusterRoleBindings. `user_list_only` are seen by the direct-user list
        call and not by the binding list call — the two calls of one refresh disagreeing."""
        from gsd import poller
        from gsd.config import ClusterConfig
        from gsd.kube import _user_binding_views

        class FakeClient:
            def __init__(self, *a, **kw): pass
            def fetch_bindings(self):
                return [v for o in objects for v in _binding_views(o, "ClusterRoleBinding")]
            def fetch_user_bindings(self):
                return [v for o in [*objects, *user_list_only] for v in _user_binding_views(o, "ClusterRoleBinding")]
            def fetch_operator_configs(self): return None

        monkeypatch.setattr(poller, "ClusterClient", FakeClient)
        poller.refresh_bindings(store, ClusterConfig("crc", "https://x", token_env="T"), timeout=5)

    @staticmethod
    def _alert_subjects(store, include_acknowledged=False):
        from datetime import UTC, datetime, timedelta as td
        import gsd.state as st
        rows = (store.direct_user_bindings("crc", include_acknowledged=True) if include_acknowledged
                else store.direct_user_bindings("crc"))
        return [a.subject for a in st.compute_alerts("crc", [], [], datetime.now(UTC), td(minutes=2), user_bindings=rows)]

    def _worklist(self, store):
        return ([r["user_name"] for r in store.direct_user_bindings("crc")],
                store.count_direct_user_bindings("crc"),
                [(r["namespace"], r["users"]) for r in store.user_bindings_by_namespace("crc")])

    def test_t503_1_a_labelled_grant_leaves_the_worklist_and_the_alert_and_is_counted(self, store, monkeypatch):
        self._refresh(store, monkeypatch, [
            self._crb("jdoe-edit", "jdoe", labels={"rbac.ocp.io/config-source": "team-x"}),
            self._crb("asmith-edit", "asmith")])
        assert self._worklist(store) == (["asmith"], 1, [("(cluster-scoped)", ["asmith"])])
        assert self._alert_subjects(store) == ["1 direct user grant"]
        assert self._alert_subjects(store, include_acknowledged=True) == ["1 direct user grant"], (
            "the alert drops a row that says it is acknowledged, whoever hands it the rows")
        assert store.acknowledged_user_binding_count("crc") == 1
        assert [(r["user_name"], r["binding_name"], r["managed_source"], r["exception"])
                for r in store.acknowledged_user_bindings("crc")] == [("jdoe", "jdoe-edit", "team-x", None)]
        assert store.platform_user_binding_count("crc") == 0

    def test_t503_2_the_exception_annotation_alone_acknowledges_it(self, store, monkeypatch):
        self._refresh(store, monkeypatch, [
            self._crb("jdoe-edit", "jdoe", annotations={"rbac.ocp.io/unmanaged-exception": "vendor access, TICKET-1"}),
            self._crb("asmith-edit", "asmith")])
        assert self._worklist(store) == (["asmith"], 1, [("(cluster-scoped)", ["asmith"])])
        assert self._alert_subjects(store) == ["1 direct user grant"]
        assert [(r["user_name"], r["managed_source"], r["exception"]) for r in store.acknowledged_user_bindings("crc")] == [
            ("jdoe", None, "vendor access, TICKET-1")]

    def test_t503_3_an_unlabelled_unannotated_grant_still_alerts(self, store, monkeypatch):
        """Regression guard against over-suppression: a Helm or OLM label, or a name, acknowledges nothing."""
        self._refresh(store, monkeypatch, [
            self._crb("jdoe-edit", "jdoe", labels={"app.kubernetes.io/managed-by": "Helm",
                                                  "olm.owner": "x"}),
            self._crb("asmith-edit", "asmith")])
        assert self._worklist(store) == (["asmith", "jdoe"], 2, [("(cluster-scoped)", ["asmith", "jdoe"])])
        assert self._alert_subjects(store) == ["2 direct user grants"]

    def test_t503_7_a_platform_identity_stays_platform_when_its_binding_is_labelled(self, store, monkeypatch):
        """Platform wins, as in the finding, where built_in is decided before provenance: excluded_platform
        keeps its meaning and its count."""
        self._refresh(store, monkeypatch, [
            self._crb("ka", "kubeadmin", role="cluster-admin", labels={"rbac.ocp.io/config-source": "team-x"})])
        assert store.platform_user_binding_count("crc") == 1
        assert store.acknowledged_user_binding_count("crc") == 0 and store.acknowledged_user_bindings("crc") == []
        assert [(r["user_name"], r["is_platform"], r["acknowledged"])
                for r in store.direct_user_bindings("crc", include_platform=True)] == [("kubeadmin", 1, 0)]

    def test_a_binding_seen_by_one_list_call_and_not_the_other_keeps_alerting(self, store, monkeypatch):
        """The two tables come from two list calls of one refresh (poller.refresh_bindings). A labelled binding
        the direct-user list saw and the binding list did not has no stored provenance, so it stays a grant to
        review: the alerting direction, until the next refresh reads both."""
        labelled = self._crb("jdoe-edit", "jdoe", labels={"rbac.ocp.io/config-source": "team-x"})
        self._refresh(store, monkeypatch, [], user_list_only=[labelled])
        assert self._worklist(store) == (["jdoe"], 1, [("(cluster-scoped)", ["jdoe"])])
        assert self._alert_subjects(store) == ["1 direct user grant"]
        assert store.acknowledged_user_binding_count("crc") == 0
        self._refresh(store, monkeypatch, [labelled])
        assert self._worklist(store) == ([], 0, []) and self._alert_subjects(store) == []
        assert store.acknowledged_user_binding_count("crc") == 1

    def test_the_view_and_the_finding_read_one_rule(self, store, monkeypatch):
        """For every person's row, acknowledged here exactly when the unmanaged finding says `ok` — an empty
        label value included, which Kubernetes allows and the finding already honours (IS NOT NULL)."""
        self._refresh(store, monkeypatch, [
            self._crb("a", "ann", labels={"rbac.ocp.io/config-source": ""}),
            self._crb("b", "bob", labels={"rbac.ocp.io/config-source": "group-sync-operator-helm"}),
            self._crb("c", "cat", annotations={"rbac.ocp.io/unmanaged-exception": "break-glass"}),
            self._crb("d", "dan")])
        finding = {r["group_name"]: r["finding"] for r in store.all_bindings("crc") if r["subject_kind"] == "User"}
        acknowledged = {r["user_name"] for r in store.acknowledged_user_bindings("crc")}
        assert finding == {"ann": "ok", "bob": "ok", "cat": "ok", "dan": "unmanaged"}
        assert acknowledged == {u for u, f in finding.items() if f == "ok"}
        assert [r["user_name"] for r in store.direct_user_bindings("crc")] == ["dan"]

    def test_a_persons_own_grants_keep_the_acknowledged_ones(self, store, monkeypatch):
        """The self tier and Home ask with include_acknowledged: an acknowledged grant is still access held."""
        self._refresh(store, monkeypatch, [self._crb("jdoe-edit", "jdoe", labels={"rbac.ocp.io/config-source": "team-x"})])
        assert store.direct_user_bindings("crc", user_name="jdoe") == []
        own = store.direct_user_bindings("crc", user_name="jdoe", include_acknowledged=True)
        assert [(r["user_name"], r["acknowledged"]) for r in own] == [("jdoe", 1)]
        assert store.count_direct_user_bindings("crc", user_name="jdoe", include_acknowledged=True) == 1

    def test_the_join_matches_each_grant_to_its_own_binding_row(self, store, monkeypatch):
        """The provenance join matches the whole primary key: the cluster, the binding (kind, namespace, name)
        and the User subject. Each pair below differs from its neighbour in one of those only, so a join that
        dropped one would lend a label to the wrong grant or count one grant twice."""
        from gsd import poller
        from gsd.config import ClusterConfig
        from gsd.kube import _user_binding_views

        def rb(ns, name, subjects, labelled):
            labels = {"rbac.ocp.io/config-source": "team-x"} if labelled else {}
            return {"kind": "RoleBinding", "metadata": {"name": name, "namespace": ns, "labels": labels},
                    "roleRef": {"kind": "ClusterRole", "name": "edit"}, "subjects": subjects}

        def user(name):
            return {"kind": "User", "name": name}

        objects = {"crc": [rb("ns-a", "edit", [user("jdoe")], True), rb("ns-b", "edit", [user("jdoe")], False),
                           rb("ns-c", "bob-a", [user("bob")], True), rb("ns-c", "bob-b", [user("bob")], False),
                           rb("ns-d", "pair", [user("ann"), user("cat")], True),
                           rb("ns-e", "dev", [{"kind": "Group", "name": "dev"}, user("dev")], True),
                           rb("ns-f", "builder", [{"kind": "ServiceAccount", "name": "builder", "namespace": "ci"},
                                                  user("builder")], True),
                           rb("ns-g", "shared", [user("eve")], True)],
                   "other": [rb("ns-g", "shared", [user("eve")], False)]}

        class FakeClient:
            def __init__(self, cluster, timeout):
                self.objects = objects[cluster.name]
            def fetch_bindings(self):
                return [v for o in self.objects for v in _binding_views(o, o["kind"])]
            def fetch_user_bindings(self):
                return [v for o in self.objects for v in _user_binding_views(o, o["kind"])]
            def fetch_operator_configs(self): return None

        monkeypatch.setattr(poller, "ClusterClient", FakeClient)
        store.upsert_cluster("other", "https://y", True)
        for name in ("crc", "other"):
            poller.refresh_bindings(store, ClusterConfig(name, "https://x", token_env="T"), timeout=5)
        key = lambda rows: sorted((r["binding_namespace"], r["binding_name"], r["user_name"]) for r in rows)  # noqa: E731
        acknowledged = [("ns-a", "edit", "jdoe"), ("ns-c", "bob-a", "bob"), ("ns-d", "pair", "ann"), ("ns-d", "pair", "cat"),
                        ("ns-e", "dev", "dev"), ("ns-f", "builder", "builder"), ("ns-g", "shared", "eve")]
        to_review = [("ns-b", "edit", "jdoe"), ("ns-c", "bob-b", "bob")]
        assert key(store.acknowledged_user_bindings("crc")) == acknowledged
        assert store.acknowledged_user_binding_count("crc") == 7
        assert key(store.direct_user_bindings("crc")) == to_review and store.count_direct_user_bindings("crc") == 2
        assert key(store.direct_user_bindings("crc", include_acknowledged=True)) == sorted(acknowledged + to_review)
        assert key(store.direct_user_bindings("other")) == [("ns-g", "shared", "eve")]
        assert store.acknowledged_user_binding_count("other") == 0

    def test_every_provenance_query_searches_rbac_group_binding_by_its_primary_key(self, store, monkeypatch):
        """Each query that reads _USER_PROVENANCE must look up a grant's own row by rbac_group_binding's
        whole primary key, never read the subquery by materializing it: that is a SCAN of every subject
        row on the cluster, ServiceAccounts and Groups included, plus an automatic index. SQLite never
        flattens a subquery on the right of a LEFT JOIN into a DISTINCT query (optoverview.html,
        flattening constraint 3), and a join that loses a key column loses the full SEARCH too."""
        import sqlite3
        if sqlite3.sqlite_version_info < (3, 40, 0):
            pytest.skip("SQLite flattens a LEFT JOIN's subquery under an aggregate from 3.40.0 (select.c, rule 3c)")
        self._refresh(store, monkeypatch, [
            self._crb("jdoe-edit", "jdoe", labels={"rbac.ocp.io/config-source": "team-x"}),
            self._crb("asmith-edit", "asmith")])
        real, seen = Store._rows, []

        def recording(self_, sql, params=()):
            seen.append((sql, tuple(params)))
            return real(self_, sql, params)

        monkeypatch.setattr(Store, "_rows", recording)
        store.direct_user_bindings("crc", limit=10)
        store.count_direct_user_bindings("crc")
        store.user_bindings_by_namespace("crc")
        store.acknowledged_user_bindings("crc", limit=10)
        store.acknowledged_user_binding_count("crc")
        store.namespaces("crc")
        store.namespace_detail("crc", "")
        joined = [(sql, params) for sql, params in seen if "ack_cluster" in sql]
        assert len(joined) == 9, len(joined)
        search = ("SEARCH rbac_group_binding USING INDEX sqlite_autoindex_rbac_group_binding_1 (cluster_id=? AND "
                  "binding_kind=? AND binding_namespace=? AND binding_name=? AND subject_kind=? AND "
                  "subject_namespace=? AND group_name=?)")
        for sql, params in joined:
            plan = [r["detail"] for r in real(store, "EXPLAIN QUERY PLAN " + sql, params)]
            assert any(line.startswith(search) for line in plan), (plan, sql)
            assert not any(line.startswith(("SCAN rbac_group_binding", "MATERIALIZE")) or "AUTOMATIC" in line
                           for line in plan), (plan, sql)


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


class TestPlatformUsersReachEveryReader:
    """#255: a user the estate names in `platformUsers` is the platform's everywhere the stored flag reaches —
    the direct-user rows, their total, the excluded count and the alert — because the poller classifies the
    User rows from the settings at each binding refresh (the reader has none)."""

    BIND = "ocp-oauth-bind-serviceid"

    def _refresh(self, store, monkeypatch, users=None):
        from gsd import poller
        from gsd.config import ClusterConfig
        from gsd.kube import UserBindingView

        class FakeClient:
            def __init__(self, *a, **kw): pass
            def fetch_bindings(self): return []
            def fetch_user_bindings(self):
                return [UserBindingView("ClusterRoleBinding", "", "poller", "ClusterRole", "poller", TestPlatformUsersReachEveryReader.BIND),
                        UserBindingView("RoleBinding", "group-sync-operator", "token-reader", "Role", "reader",
                                        TestPlatformUsersReachEveryReader.BIND),
                        UserBindingView("RoleBinding", "legacy", "jdoe-edit", "ClusterRole", "edit", "jdoe"),
                        UserBindingView("ClusterRoleBinding", "", "ka", "ClusterRole", "cluster-admin", "kubeadmin")]
            def fetch_operator_configs(self): return None

        monkeypatch.setattr(poller, "ClusterClient", FakeClient)
        poller.refresh_bindings(store, ClusterConfig("crc", "https://x", token_env="T"), timeout=5, platform_users=users)

    @staticmethod
    def _alert_subjects(store):
        from datetime import UTC, datetime, timedelta as td
        import gsd.state as st
        return [a.subject for a in st.compute_alerts("crc", [], [], datetime.now(UTC), td(minutes=2),
                                                     user_bindings=store.direct_user_bindings("crc"))]

    def test_t255_2_a_named_user_leaves_the_rows_and_the_alert_and_is_counted(self, store, monkeypatch):
        from gsd.config import PlatformUsers
        self._refresh(store, monkeypatch)
        assert sorted(r["user_name"] for r in store.direct_user_bindings("crc")) == ["jdoe", self.BIND, self.BIND]
        assert store.platform_user_binding_count("crc") == 1
        assert self._alert_subjects(store) == ["3 direct user grants"]

        self._refresh(store, monkeypatch, PlatformUsers(additional_names=frozenset({self.BIND})))
        assert [r["user_name"] for r in store.direct_user_bindings("crc")] == ["jdoe"]
        assert store.count_direct_user_bindings("crc") == 1
        assert [r["namespace"] for r in store.user_bindings_by_namespace("crc")] == ["legacy"]
        assert store.platform_user_binding_count("crc") == 3, "excluded_platform rises by exactly the two rows"
        assert self._alert_subjects(store) == ["1 direct user grant"]

        self._refresh(store, monkeypatch)
        assert store.platform_user_binding_count("crc") == 1, "removed from the list, the rows come back"

    def test_t255_3_names_replaced_makes_kubeadmin_a_person(self, store, monkeypatch):
        from gsd.config import PlatformUsers
        self._refresh(store, monkeypatch, PlatformUsers(names=frozenset()))
        assert "kubeadmin" in {r["user_name"] for r in store.direct_user_bindings("crc")}
        assert store.platform_user_binding_count("crc") == 0

    def test_a_reclassification_records_no_binding_event(self, store, monkeypatch):
        """Moving a user between "a person" and "the platform" changes what is counted, not what is granted:
        the event stream compares the role only (store.py _append_binding_events), so it stays silent."""
        from gsd.config import PlatformUsers
        self._refresh(store, monkeypatch)
        before = store.binding_events("crc")
        self._refresh(store, monkeypatch, PlatformUsers(additional_names=frozenset({self.BIND})))
        assert store.binding_events("crc") == before
