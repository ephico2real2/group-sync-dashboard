"""The unmanaged finding on ServiceAccount and User subjects (#353, docs/specs/SPEC_U1_unmanaged_subjects.md).

The operator's rule, tested layer by layer: a grant is excluded ONLY by the `rbac.ocp.io/config-source`
label or the `rbac.ocp.io/unmanaged-exception` annotation on its binding, whoever it names; nothing
about how it was applied — a `system:` name, a platform namespace, a Helm or OLM label — excludes it.
The Group-only questions (a group's page, a person's access through groups, the namespace audit, the
history stream) never see the new kinds. Every test here fails on the tree before SPEC_U1.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.audit import plan_audit_stamps, subject_label
from gsd.config import ClusterConfig, Settings
from gsd.kube import CHART_CONFIG_SOURCE, SUBJECT_KINDS, BindingView, _binding_views
from gsd.store import Store, _MIGRATIONS

T = "2026-09-24T20:00:00Z"
SYNCED = "app-ocp-rbac-team-ns-admin"


@pytest.fixture()
def store():
    s = Store(":memory:")
    s.upsert_cluster("crc", "https://x", True)
    yield s
    s.close()


def _synced(store, *names):
    """Groups the operator syncs: a Group object and a sync record for each."""
    store.replace_group_state(
        "crc", [{"name": n, "member_count": 1, "sync_provider": "ldap-groupsync_ldap",
                 "group_synced_at": None, "ldap_uid": None} for n in names], T)
    store.record_managed_groups("crc", [{"name": n, "sync_provider": "ldap-groupsync_ldap"} for n in names], T)


def group(name, subject=SYNCED, **kw):
    return {"binding_kind": "RoleBinding", "binding_namespace": "ns-a", "binding_name": name,
            "role_kind": "ClusterRole", "role_name": "admin", "group_name": subject, **kw}


def sa(name, account="poller", namespace="group-sync-operator", **kw):
    return {"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": name,
            "role_kind": "ClusterRole", "role_name": "cluster-admin", "group_name": account,
            "subject_kind": "ServiceAccount", "subject_namespace": namespace, **kw}


def user(name, person="tmp-contractor-9931", **kw):
    return {"binding_kind": "RoleBinding", "binding_namespace": "ldap-testing", "binding_name": name,
            "role_kind": "ClusterRole", "role_name": "edit", "group_name": person,
            "subject_kind": "User", "subject_namespace": "", **kw}


def findings(store):
    return {r["binding_name"]: r["finding"] for r in store.all_bindings("crc")}


class TestReader:
    def _obj(self, kind, subjects, namespace="alpha"):
        meta = {"name": "b"} if kind == "ClusterRoleBinding" else {"name": "b", "namespace": namespace}
        return {"metadata": meta, "roleRef": {"kind": "ClusterRole", "name": "edit"}, "subjects": subjects}

    def test_a_rolebinding_serviceaccount_with_no_namespace_is_stored_under_the_bindings(self):
        """rule.go appliesToUser: the authorizer reads an omitted namespace as the binding's own, so the
        row names the account RBAC matches. 26 of the lab's 685 ServiceAccount subjects omit it."""
        rows = _binding_views(self._obj("RoleBinding", [{"kind": "ServiceAccount", "name": "builder"}]), "RoleBinding")
        assert [(r.subject_kind, r.subject_namespace, r.group_name) for r in rows] == [("ServiceAccount", "alpha", "builder")]

    def test_a_serviceaccount_that_names_a_namespace_keeps_its_own(self):
        rows = _binding_views(self._obj("RoleBinding", [{"kind": "ServiceAccount", "name": "builder", "namespace": "other"}]),
                              "RoleBinding")
        assert rows[0].subject_namespace == "other"
        rows = _binding_views(self._obj("ClusterRoleBinding", [{"kind": "ServiceAccount", "name": "poller",
                                                                "namespace": "group-sync-operator"}]), "ClusterRoleBinding")
        assert (rows[0].binding_namespace, rows[0].subject_namespace) == ("", "group-sync-operator")

    def test_users_and_groups_carry_no_namespace_and_unknown_kinds_nothing(self):
        rows = _binding_views(self._obj("RoleBinding", [
            {"kind": "User", "name": "alice"}, {"kind": "Group", "name": "g"},
            {"kind": "Robot", "name": "r2"}, {"kind": "ServiceAccount"}]), "RoleBinding")
        assert [(r.subject_kind, r.subject_namespace, r.group_name) for r in rows] == [
            ("User", "", "alice"), ("Group", "", "g")]
        assert SUBJECT_KINDS == ("Group", "ServiceAccount", "User")

    def test_a_view_built_the_old_way_is_a_group(self):
        v = BindingView("RoleBinding", "ns", "b", "ClusterRole", "r", "some-group")
        assert (v.subject_kind, v.subject_namespace) == ("Group", "")


class TestClassification:
    def test_an_unlabelled_serviceaccount_grant_is_unmanaged_where_the_policy_operator_is_in_use(self, store):
        _synced(store, SYNCED)
        store.replace_bindings("crc", [group("managed", managed_source="prod-rbac"), sa("hand-made-sa")], T)
        assert findings(store) == {"managed": "ok", "hand-made-sa": "unmanaged"}
        assert store.count_bindings_by_finding("crc")["unmanaged"] == 1

    def test_the_operators_label_on_the_binding_silences_it(self, store):
        _synced(store, SYNCED)
        store.replace_bindings("crc", [group("managed", managed_source="prod-rbac"),
                                       sa("decided", managed_source="platform-team"),
                                       user("person-decided", managed_source="platform-team")], T)
        assert findings(store) == {"managed": "ok", "decided": "ok", "person-decided": "ok"}

    def test_the_exception_annotation_silences_it(self, store):
        _synced(store, SYNCED)
        store.replace_bindings("crc", [group("managed", managed_source="prod-rbac"),
                                       sa("break-glass", exception="approved in TICKET-123")], T)
        assert findings(store)["break-glass"] == "ok"

    def test_a_system_named_user_is_unmanaged_and_never_built_in(self, store):
        """No inference from a `system:` name: the built_in tier is a Group tier. The lab's
        `system:kube-scheduler` User grants (6) are findings until labelled."""
        _synced(store, SYNCED)
        store.replace_bindings("crc", [group("managed", managed_source="prod-rbac"),
                                       user("scheduler", person="system:kube-scheduler"),
                                       group("virtual", subject="system:authenticated")], T)
        assert findings(store) == {"managed": "ok", "scheduler": "unmanaged", "virtual": "built_in"}

    def test_the_charts_own_label_silences_only_its_own_accounts(self, store):
        """#354 carried over for the Group arm: the chart labels its seven ServiceAccount bindings, and
        on a host with no policy operator a hand-made GROUP grant is not reported until one policy label
        exists. A hand-made account is reported regardless: the new kinds have no gate (Codex, review of
        SPEC_U1 — a gate silenced them by default, which the operator's rule forbids)."""
        _synced(store, SYNCED)
        chart = [sa(f"chart-{i}", account="group-sync-dashboard", namespace="group-sync-dashboard",
                    managed_source=CHART_CONFIG_SOURCE) for i in range(2)]
        store.replace_bindings("crc", chart + [sa("hand-made-sa"), group("hand-made")], T)
        assert findings(store) == {"chart-0": "ok", "chart-1": "ok", "hand-made-sa": "unmanaged", "hand-made": "ok"}
        store.replace_bindings("crc", chart + [sa("hand-made-sa"), group("hand-made"),
                                               group("managed", managed_source="prod-rbac")], T)
        assert findings(store) == {"chart-0": "ok", "chart-1": "ok", "hand-made-sa": "unmanaged",
                                   "hand-made": "unmanaged", "managed": "ok"}

    def test_an_unlabelled_account_is_a_finding_with_no_label_anywhere_on_the_cluster(self, store):
        """No gate for the new kinds: on a host with no label at all, the accounts and the person report;
        the Group grant does not, as #354 left it."""
        _synced(store, SYNCED)
        store.replace_bindings("crc", [sa("hand-made-sa"), user("hand-made-user"), group("hand-made")], T)
        assert findings(store) == {"hand-made-sa": "unmanaged", "hand-made-user": "unmanaged", "hand-made": "ok"}

    def test_a_labelled_account_does_not_open_the_group_gate(self, store):
        """The Group arm's gate reads Group rows only, so it is byte for byte #354's: the operator's label
        on an account silences that account and changes nothing for a hand-made Group grant."""
        _synced(store, SYNCED)
        store.replace_bindings("crc", [sa("decided", managed_source="platform-team"),
                                       sa("hand-made-sa"), group("hand-made")], T)
        assert findings(store) == {"decided": "ok", "hand-made-sa": "unmanaged", "hand-made": "ok"}

    def test_an_account_named_like_a_synced_group_borrows_nothing_from_it(self, store):
        """The joins to the Group object, its sync record and its members are Group-only: the
        account is judged on provenance and its reach is null, not the group's members."""
        _synced(store, SYNCED)
        store.sync_members("crc", {SYNCED: ["alice"]}, {SYNCED: T}, T)
        store.replace_bindings("crc", [group("managed", managed_source="prod-rbac"),
                                       sa("same-name", account=SYNCED, managed_source="platform-team"),
                                       sa("same-name-unlabelled", account=SYNCED)], T)
        rows = {r["binding_name"]: r for r in store.all_bindings("crc", reach=True)}
        assert rows["same-name"]["finding"] == "ok" and rows["same-name-unlabelled"]["finding"] == "unmanaged"
        assert rows["same-name"]["member_count"] is None and rows["same-name-unlabelled"]["member_count"] is None
        assert rows["managed"]["member_count"] == 1

    def test_rows_carry_their_kind_and_namespace(self, store):
        _synced(store, SYNCED)
        store.replace_bindings("crc", [group("g"), sa("s"), user("u")], T)
        rows = {r["binding_name"]: (r["subject_kind"], r["subject_namespace"], r["group_name"]) for r in store.all_bindings("crc")}
        assert rows == {"g": ("Group", "", SYNCED), "s": ("ServiceAccount", "group-sync-operator", "poller"),
                        "u": ("User", "", "tmp-contractor-9931")}


class TestGroupOnlyReaders:
    @pytest.fixture()
    def mixed(self, store):
        """A synced group `devs` with one member, bound in ns-a; an account and a person each named
        `devs` too, bound in the same namespace and cluster-wide. Every Group-only reader must answer
        as if the account and the person were not there."""
        _synced(store, "devs")
        store.sync_members("crc", {"devs": ["alice"]}, {"devs": T}, T)
        store.replace_namespaces("crc", [{"name": "ns-a", "phase": "Active", "metadata": {}}], T)
        store.replace_bindings("crc", [
            group("devs-edit", subject="devs", managed_source="prod-rbac"),
            sa("devs-sa", account="devs", namespace="ns-a"),
            {**sa("devs-sa-ns", account="devs", namespace="ns-a"), "binding_kind": "RoleBinding", "binding_namespace": "ns-a"},
            {**user("devs-user", person="devs"), "binding_namespace": "ns-a"},
        ], T)
        return store

    def test_a_groups_bindings_and_count(self, mixed):
        assert [b["binding_name"] for b in mixed.group_bindings("crc", "devs")] == ["devs-edit"]
        assert {g["name"]: g["binding_count"] for g in mixed.groups("crc")} == {"devs": 1}

    def test_a_persons_access_through_groups(self, mixed):
        assert [b["binding_name"] for b in mixed.user_bindings("crc", "alice")] == ["devs-edit"]

    def test_the_namespace_audit(self, mixed):
        ns = {n["name"]: n["via_groups"] for n in mixed.namespaces("crc")}
        assert ns == {"ns-a": 1}
        assert mixed.namespace_reach("crc", "ns-a", "alice", ["devs"]) is True
        assert mixed.namespace_reach("crc", "ns-a", "nobody", []) is False
        detail = mixed.namespace_detail("crc", "ns-a")
        assert [b["binding_name"] for b in detail["via_groups"]] == ["devs-edit"]


class TestWriter:
    def test_no_history_event_for_an_account_or_a_person_and_the_group_diff_is_unaffected(self, store):
        counts = store.replace_bindings("crc", [group("g"), sa("s"), user("u")], T)
        assert counts == {"added": 1, "removed": 0}
        assert [(e["subject_kind"], e["subject_name"]) for e in store.binding_events("crc")] == [("Group", SYNCED)]
        counts = store.replace_bindings("crc", [group("g"), sa("s2")], "2026-09-24T20:05:00Z")
        assert counts == {"added": 0, "removed": 0}

    def test_a_row_that_names_no_kind_is_a_group(self, store):
        store.replace_bindings("crc", [group("g")], T)
        row = store.all_bindings("crc")[0]
        assert (row["subject_kind"], row["subject_namespace"]) == ("Group", "")


def _v19_database(path: str) -> None:
    """A database as release 0.32.0 left it: the old table shape, one row, user_version 19."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE rbac_group_binding (
            cluster_id          TEXT NOT NULL,
            binding_kind        TEXT NOT NULL,
            binding_namespace   TEXT NOT NULL,
            binding_name        TEXT NOT NULL,
            role_kind           TEXT NOT NULL,
            role_name           TEXT NOT NULL,
            group_name          TEXT NOT NULL,
            observed_at         TEXT NOT NULL,
            managed_source      TEXT,
            exception           TEXT,
            audit_stamped       INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(cluster_id, binding_kind, binding_namespace, binding_name, group_name)
        );
        CREATE INDEX rbac_binding_by_group ON rbac_group_binding(cluster_id, group_name);
        INSERT INTO rbac_group_binding VALUES
            ('crc', 'RoleBinding', 'ns-a', 'old-row', 'ClusterRole', 'view',
             'app-ocp-rbac-team-ns-audit', '2026-09-01T00:00:00Z', 'prod-rbac', NULL, 1);
        PRAGMA user_version = 19;
    """)
    conn.commit()
    conn.close()


class TestMigration20:
    def test_the_table_is_rebuilt_and_the_rows_carried_as_group_subjects(self, tmp_path):
        db = str(tmp_path / "old.db")
        _v19_database(db)
        store = Store(db)
        try:
            cols = [r[1] for r in store._conn.execute("PRAGMA table_info(rbac_group_binding)")]
            assert "subject_kind" in cols and "subject_namespace" in cols
            pk = [r[1] for r in sorted(store._conn.execute("PRAGMA table_info(rbac_group_binding)"), key=lambda r: r[5]) if r[5]]
            assert pk == ["cluster_id", "binding_kind", "binding_namespace", "binding_name",
                          "subject_kind", "subject_namespace", "group_name"]
            rows = store.all_bindings("crc")
            assert len(rows) == 1
            assert (rows[0]["subject_kind"], rows[0]["subject_namespace"], rows[0]["group_name"],
                    rows[0]["managed_source"], rows[0]["audit_stamped"]) == ("Group", "", "app-ocp-rbac-team-ns-audit", "prod-rbac", 1)
            assert store._conn.execute("PRAGMA user_version").fetchone()[0] == 20
            assert [r[1] for r in store._conn.execute("PRAGMA index_list(rbac_group_binding)")].count("rbac_binding_by_group") == 1
        finally:
            store.close()

    def test_a_v20_table_left_populated_still_opens(self, tmp_path):
        """The replay converges from a populated rbac_group_binding_v20 beside the old table (Grok,
        review of SPEC_U1). A crash cannot produce that state — the copy, the drop and the rename ride
        one implicit transaction — but a hand repair can, and without OR IGNORE the replay raised
        IntegrityError, which _migrate does not tolerate, so the pod could not open its database."""
        db = str(tmp_path / "repaired.db")
        _v19_database(db)
        conn = sqlite3.connect(db)
        conn.executescript("""
            CREATE TABLE rbac_group_binding_v20 (
                cluster_id TEXT NOT NULL, binding_kind TEXT NOT NULL, binding_namespace TEXT NOT NULL,
                binding_name TEXT NOT NULL, role_kind TEXT NOT NULL, role_name TEXT NOT NULL,
                subject_kind TEXT NOT NULL DEFAULT 'Group', subject_namespace TEXT NOT NULL DEFAULT '',
                group_name TEXT NOT NULL, observed_at TEXT NOT NULL, managed_source TEXT, exception TEXT,
                audit_stamped INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(cluster_id, binding_kind, binding_namespace, binding_name,
                            subject_kind, subject_namespace, group_name));
            INSERT INTO rbac_group_binding_v20
                SELECT cluster_id, binding_kind, binding_namespace, binding_name, role_kind, role_name,
                       'Group', '', group_name, observed_at, managed_source, exception, audit_stamped
                  FROM rbac_group_binding;
        """)
        conn.commit(); conn.close()
        store = Store(db)
        try:
            assert store._conn.execute("PRAGMA user_version").fetchone()[0] == 20
            rows = store.all_bindings("crc")
            assert len(rows) == 1
            assert (rows[0]["group_name"], rows[0]["managed_source"], rows[0]["audit_stamped"]) == (
                "app-ocp-rbac-team-ns-audit", "prod-rbac", 1)
        finally:
            store.close()

    def test_reopening_is_idempotent_and_the_report_service_knows_the_version(self, tmp_path):
        from gsd.reporting.snapshot import KNOWN_SCHEMA_VERSION
        db = str(tmp_path / "old.db")
        _v19_database(db)
        for _ in range(3):
            Store(db).close()
        store = Store(db)
        try:
            assert store._conn.execute("PRAGMA user_version").fetchone()[0] == max(t for t, _, _ in _MIGRATIONS) == 20
            assert len(store.all_bindings("crc")) == 1
        finally:
            store.close()
        assert KNOWN_SCHEMA_VERSION == 20


class TestAnnouncer:
    def test_subject_label_spells_the_three_kinds(self):
        assert subject_label({"group_name": "g"}) == "group g"
        assert subject_label({"subject_kind": "Group", "group_name": "g"}) == "group g"
        assert subject_label({"subject_kind": "ServiceAccount", "subject_namespace": "ns", "group_name": "a"}) == "ServiceAccount ns/a"
        assert subject_label({"subject_kind": "User", "group_name": "p"}) == "user p"

    def test_the_evidence_names_the_account_and_only_the_unmanaged_subject(self):
        row = {"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "poller-crb",
               "role_name": "cluster-admin", "audit_stamped": False}
        plan = plan_audit_stamps([
            {**row, "subject_kind": "ServiceAccount", "subject_namespace": "group-sync-operator",
             "group_name": "shared-qa-poller", "finding": "unmanaged"},
            {**row, "subject_kind": "Group", "subject_namespace": "", "group_name": "labelled-group", "finding": "ok"},
        ])
        key = ("ClusterRoleBinding", "", "poller-crb")
        assert plan.stamp == [key]
        assert plan.evidence[key] == {"role": "cluster-admin", "subjects": ["ServiceAccount group-sync-operator/shared-qa-poller"]}

    def test_one_refresh_logs_the_account_and_stores_the_stamp_it_read(self, tmp_path, monkeypatch, caplog):
        from gsd import poller
        store = Store(str(tmp_path / "t.db"))
        store.upsert_cluster("c1", "https://x", True)
        _synced_c1 = [{"name": SYNCED, "sync_provider": "gs_ldap"}]
        store.record_managed_groups("c1", _synced_c1, T)
        store.replace_group_state("c1", [{"name": SYNCED, "member_count": 1, "sync_provider": "gs_ldap",
                                          "group_synced_at": None, "ldap_uid": None}], T)
        # The labelled Group binding carries the rbac.ocp.io/unmanaged label (audit_stamped): it is `ok`, so
        # the plan RESOLVES it (I4) — and the stamp reaches the store, which it never did before SPEC_U1.
        # The account is unlabelled and unstamped, so it is announced (I3 never re-announces a stamped one).
        rows = [
            BindingView("RoleBinding", "ns", "managed", "ClusterRole", "admin", SYNCED, managed_source="policy",
                        audit_stamped=True),
            BindingView("ClusterRoleBinding", "", "shared-qa-poller", "ClusterRole", "cluster-admin", "shared-qa-poller",
                        subject_kind="ServiceAccount", subject_namespace="group-sync-operator"),
        ]

        class FakeClient:
            def __init__(self, *a, **kw): pass
            def fetch_bindings(self): return rows
            def fetch_user_bindings(self): return []
            def fetch_operator_configs(self): return None

        monkeypatch.setattr(poller, "ClusterClient", FakeClient)
        with caplog.at_level("INFO", logger="gsd.poller"):
            poller.refresh_bindings(store, ClusterConfig("c1", "https://x", token_env="T"), timeout=5, audit_mode="log")
        assert "grants cluster-admin to ServiceAccount group-sync-operator/shared-qa-poller" in caplog.text, caplog.text
        assert "unmanaged grant RESOLVED — c1: RoleBinding ns/managed" in caplog.text, caplog.text
        assert "1 outside the policy system, 1 resolved" in caplog.text, caplog.text
        assert "refreshed 2 bindings for c1 (1 Group, 1 ServiceAccount, 0 User subjects)" in caplog.text, caplog.text
        stamped = {r["binding_name"]: r["audit_stamped"] for r in store.all_bindings("c1")}
        assert stamped == {"managed": 1, "shared-qa-poller": 0}
        store.close()


class TestApi:
    @pytest.fixture()
    def client(self, tmp_path):
        db = str(tmp_path / "t.db")
        store = Store(db)
        store.upsert_cluster("c1", "https://x", True)
        store.replace_group_state("c1", [{"name": SYNCED, "member_count": 1, "sync_provider": "gs_ldap",
                                          "group_synced_at": None, "ldap_uid": None}], T)
        store.record_managed_groups("c1", [{"name": SYNCED, "sync_provider": "gs_ldap"}], T)
        store.replace_bindings("c1", [group("managed", managed_source="prod-rbac"),
                                      sa("shared-qa-poller", account="shared-qa-poller")], T)
        store.close()
        settings = Settings(db_path=db, clusters=[ClusterConfig("c1", "https://x", token_env="T")])
        return TestClient(build_app(settings, run_poller=False))

    def test_a_finding_row_carries_its_kind_and_the_cluster_counts_it(self, client):
        d = client.get("/api/clusters/c1/bindings/findings").json()
        assert d["counts"]["unmanaged"] == 1 and d["counts"]["ok"] == 1
        row = d["unmanaged"][0]
        assert (row["subject_kind"], row["subject_namespace"], row["group_name"]) == ("ServiceAccount", "group-sync-operator", "shared-qa-poller")
        assert row["member_count"] is None and row["logged_in_count"] is None
        assert d["ok"][0]["subject_kind"] == "Group"
        clusters = {c["id"]: c for c in client.get("/api/clusters").json()}
        assert clusters["c1"]["unmanaged_bindings"] == 1


class TestReports:
    @pytest.fixture()
    def snap(self, tmp_path):
        from gsd.reporting.snapshot import Snapshot
        store = Store(str(tmp_path / "w.db"))
        store.upsert_cluster("crc", "https://x", True)
        _synced(store, SYNCED)
        store.replace_bindings("crc", [
            group("managed", managed_source="prod-rbac"),
            sa("shared-qa-poller", account="shared-qa-poller"),
            user("scheduler", person="system:kube-scheduler"),
            group("virtual", subject="system:authenticated"),
        ], T)
        d = tmp_path / "snapshots"; d.mkdir()
        path = store.snapshot(str(d), keep=2)
        store.close()
        s = Snapshot(Path(path))
        yield s
        s.close()

    def test_the_snapshot_lists_groups_by_default_and_every_kind_on_request(self, snap):
        assert [r["binding_name"] for r in snap.group_bindings("crc")] == ["managed"]
        rows = {r["binding_name"]: r for r in snap.group_bindings("crc", kinds=SUBJECT_KINDS)}
        assert set(rows) == {"managed", "shared-qa-poller", "scheduler"}, "the virtual group is omitted, the system-named user is not"
        assert rows["shared-qa-poller"]["finding"] == "unmanaged" and rows["scheduler"]["finding"] == "unmanaged"
        assert rows["shared-qa-poller"]["member_count"] is None
        assert snap.findings_counts("crc") == {"ok": 1, "unmanaged": 2}
        assert snap.counts("crc")["group_bindings"] == 1

    @staticmethod
    def _build(snap, name):
        from gsd.reporting.catalogue import REGISTRY, RunContext, validate_params
        from gsd.reporting.config import ReportSettings
        from datetime import UTC, datetime
        vendor = Path(__file__).resolve().parents[1] / "gsd" / "static" / "vendor"
        settings = ReportSettings(pdf_enabled=False, pdf_variant="pdf/a-2b", font_regular=str(vendor / "DejaVuSans.ttf"),
                                  font_bold=str(vendor / "DejaVuSans-Bold.ttf"), login_capture_enabled=False,
                                  namespaces_read_enabled=False)
        info = snap.info()
        now = datetime(2026, 9, 24, 20, 0, tzinfo=UTC)
        ctx = RunContext(settings=settings, cluster=snap.cluster("crc"), now=now, run_id="20260924T200000.000000Z-ab12",
                         generated_by="root", generated_by_note="proxy-verified", snapshot_stamp=info.stamp,
                         snapshot_age_seconds=info.age_seconds(now), schema_version=info.schema_version)
        spec, build = REGISTRY[name]
        return build(snap, ctx, validate_params(spec, {}))

    def test_the_binding_findings_report_names_the_account(self, snap):
        built = self._build(snap, "binding-findings")
        unmanaged = next(b for s in built.sections if s.title == "Unmanaged bindings" for b in s.blocks)
        assert unmanaged.columns[0] == "subject"
        subjects = sorted(r[0] for r in unmanaged.rows)
        assert subjects == ["ServiceAccount group-sync-operator/shared-qa-poller", "user system:kube-scheduler"]
        assert built.totals["unmanaged"] == 2

    def test_the_compliance_snapshot_names_its_two_populations(self, snap):
        """The group figure counts Group subjects; the Unmanaged figure counts every kind (Grok, review
        of SPEC_U1): 1 beside 2 on this seed, which read as two of one binding under the old labels."""
        built = self._build(snap, "compliance-snapshot")
        rbac = next(b for s in built.sections if s.title == "Key figures" for b in s.blocks if getattr(b, "title", None) == "RBAC")
        figures = dict(rbac.items)
        assert figures["Group bindings (Group subjects)"] == 1
        assert figures["Unmanaged (every subject kind)"] == 2
        # The every-kind total the Unmanaged figure is a part of (OB1-lite): 3 here, not the 1 Group binding.
        assert figures["Bindings (every subject kind)"] == 3
        assert figures["Unmanaged (every subject kind)"] <= figures["Bindings (every subject kind)"]
        assert "Platform identity grants (excluded from the direct-user figures)" in figures
        assert "Group bindings" not in figures and "Unmanaged" not in figures


class TestDuplicateSubjects:
    def test_a_subject_named_twice_on_one_binding_is_one_row(self):
        """OLM writes some RoleBindings with the same ServiceAccount twice (10 on the lab, e.g.
        metallb-system/metallb-operator.v4.22.0-202609151747 naming four accounts twice). The authorizer
        grants it once and the store's primary key keeps one row, so the reader must yield one — or the
        refresh line counts 925 subjects while the store holds 915 (OB1-lite, review of SPEC_U1)."""
        obj = {"metadata": {"name": "op.v1", "namespace": "alpha"},
               "roleRef": {"kind": "Role", "name": "op.v1"},
               "subjects": [{"kind": "ServiceAccount", "name": "controller"},
                            {"kind": "ServiceAccount", "name": "controller"},
                            {"kind": "ServiceAccount", "name": "controller", "namespace": "alpha"},
                            {"kind": "Group", "name": "g"}, {"kind": "Group", "name": "g"}]}
        rows = _binding_views(obj, "RoleBinding")
        assert [(r.subject_kind, r.subject_namespace, r.group_name) for r in rows] == [
            ("ServiceAccount", "alpha", "controller"), ("Group", "", "g")]


class TestSeverityFirstPage:
    def test_a_page_of_findings_holds_the_review_tiers_before_the_rest(self, store):
        """all_bindings(limit=…) is the page the Access granted and RBAC policy tabs render. Ordered by
        subject name alone, 500 unmanaged ServiceAccount rows named `aa…` pushed a dangling group named
        `zz…` off the page; severity first keeps every review item ahead of ok and built-in."""
        store.record_managed_groups("crc", [{"name": "zz-was-synced", "sync_provider": "ldap"},
                                            {"name": SYNCED, "sync_provider": "ldap"}], T)
        store.replace_group_state("crc", [{"name": SYNCED, "member_count": 1, "sync_provider": "ldap",
                                           "group_synced_at": None, "ldap_uid": None}], T)
        rows = [group("managed", managed_source="prod-rbac"), group("gone", subject="zz-was-synced")]
        rows += [sa(f"sa-{i}", account=f"aa-{i:03d}", namespace="ns") for i in range(3)]
        store.replace_bindings("crc", rows, T)
        page = [r["finding"] for r in store.all_bindings("crc", limit=2, offset=0)]
        assert page == ["dangling", "unmanaged"], page
        assert [r["finding"] for r in store.all_bindings("crc")] == ["dangling", "unmanaged", "unmanaged", "unmanaged", "ok"]


class TestAnOlderCopyInTheRollingWindow:
    def test_a_copy_written_before_migration_20_is_read_as_group_rows(self, tmp_path):
        """The report service accepts an OLDER copy by design (only a newer one is refused): while the
        pods roll, the newest snapshot on the volume is the 0.32.0 dashboard's, schema 19, until the new
        dashboard writes one. Every binding read now names subject_kind; against that copy each one raised
        "no such column: b.subject_kind" — a 500 on preview, a failed run — instead of reading the Group
        rows the copy holds (OB1-lite, review of SPEC_U1)."""
        from gsd.reporting.snapshot import Snapshot
        store = Store(str(tmp_path / "live.db"))
        store.upsert_cluster("crc", "https://x", True)
        _synced(store, SYNCED)
        store.replace_bindings("crc", [group("managed", managed_source="prod-rbac"), group("hand-made")], T)
        d = tmp_path / "snapshots"; d.mkdir()
        path = store.snapshot(str(d), keep=2)
        store.close()
        # The copy as release 0.32.0 wrote it: migration 20's one change undone, user_version 19.
        conn = sqlite3.connect(path)
        conn.executescript("""
            CREATE TABLE old AS SELECT cluster_id, binding_kind, binding_namespace, binding_name, role_kind,
                                       role_name, group_name, observed_at, managed_source, exception, audit_stamped
                                  FROM rbac_group_binding;
            DROP TABLE rbac_group_binding;
            ALTER TABLE old RENAME TO rbac_group_binding;
            PRAGMA user_version = 19;""")
        conn.commit(); conn.close()
        with Snapshot(Path(path)) as s:
            assert s.schema_version == 19
            assert s.findings_counts("crc") == {"ok": 1, "unmanaged": 1}
            assert s.counts("crc")["group_bindings"] == 2
            rows = s.group_bindings("crc", kinds=SUBJECT_KINDS)
            assert {(r["binding_name"], r["subject_kind"], r["subject_namespace"]) for r in rows} == {
                ("managed", "Group", ""), ("hand-made", "Group", "")}
            assert {g["name"]: g["bindings"] for g in s.groups("crc")} == {SYNCED: 2}


class TestRolePicker:
    def test_a_role_bound_only_to_an_account_is_not_offered(self, tmp_path):
        """The report form's role picker (privileged-access `roles`) matches Group rows and direct user
        grants only. Reading every subject kind offered roles no report that takes the list can match —
        on the lab 356 distinct roles where 66 can (OB1-lite, review of SPEC_U1)."""
        from gsd.reporting.snapshot import Snapshot
        store = Store(str(tmp_path / "w.db"))
        store.upsert_cluster("crc", "https://x", True)
        store.replace_bindings("crc", [group("team-admin"),
                                       sa("scc", account="builder", namespace="ci") | {"role_name": "system:openshift:scc:privileged"}], T)
        d = tmp_path / "snapshots"; d.mkdir()
        path = store.snapshot(str(d), keep=2)
        store.close()
        with Snapshot(Path(path)) as s:
            assert s.discovered("crc", "", "")["roles"]["values"] == ["admin"]


class TestTotalOrder:
    """A page and a report are ordered by the whole primary key. Before #353 the ORDER BY (subject name,
    binding kind, namespace, name) named every key column; migration 20 added subject_kind and
    subject_namespace to the key, and one binding can now name `x` twice — as ServiceAccounts in two
    namespaces (the lab's system:controller:horizontal-pod-autoscaler names kube-system/ and
    openshift-infra/horizontal-pod-autoscaler), or as an account and a user. Rows that tie on the ORDER BY
    come back in whatever order SQLite scans them, so neither `/bindings/findings`' limit/offset walk nor
    a report's row order was defined by content (OB1-lite, second pass of SPEC_U1)."""

    def _rows(self):
        hpa = "horizontal-pod-autoscaler"
        # Inserted in the reverse of content order, so an order that falls back on the scan shows it.
        return [user("same", person=hpa) | {"binding_kind": "ClusterRoleBinding", "binding_namespace": "",
                                            "binding_name": "system:controller:hpa"},
                sa("system:controller:hpa", account=hpa, namespace="openshift-infra"),
                sa("system:controller:hpa", account=hpa, namespace="kube-system")]

    def test_the_findings_page_orders_ties_by_subject_kind_and_namespace(self, store):
        store.replace_bindings("crc", self._rows(), T)
        want = [("ServiceAccount", "kube-system"), ("ServiceAccount", "openshift-infra"), ("User", "")]
        assert [(r["subject_kind"], r["subject_namespace"]) for r in store.all_bindings("crc")] == want
        walked = [(r["subject_kind"], r["subject_namespace"])
                  for o in range(3) for r in store.all_bindings("crc", limit=1, offset=o)]
        assert walked == want

    def test_a_report_orders_ties_by_subject_kind_and_namespace(self, tmp_path):
        from gsd.reporting.snapshot import Snapshot
        live = Store(str(tmp_path / "w.db"))
        live.upsert_cluster("crc", "https://x", True)
        live.replace_bindings("crc", self._rows(), T)
        d = tmp_path / "snapshots"; d.mkdir()
        path = live.snapshot(str(d), keep=2)
        live.close()
        with Snapshot(Path(path)) as s:
            rows = s.group_bindings("crc", kinds=SUBJECT_KINDS)
        assert [(r["subject_kind"], r["subject_namespace"]) for r in rows] == [
            ("ServiceAccount", "kube-system"), ("ServiceAccount", "openshift-infra"), ("User", "")]
