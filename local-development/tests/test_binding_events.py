"""binding_event: the bindings' membership history (docs/DESIGN_binding_events.md).

The claims, each with a test: a refresh records what appeared and disappeared, a role change is
one removed + one added, an unchanged refresh records nothing, a cluster's first observation is
flagged baseline, user and group subjects are independent, retention prunes it like the other
history tables, the metric counts without naming anyone, and the wire says what it is.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.config import ClusterConfig, Settings
from gsd.metrics import BINDING_CHANGES, BINDING_SUBJECT_KINDS, RETENTION_TABLES, RuntimeSignals, build_registry
from gsd.store import Store

T1 = "2026-09-17T22:00:00Z"
T2 = "2026-09-17T22:05:00Z"
T3 = "2026-09-17T22:10:00Z"


def rb(name, ns, group, role="edit", kind="RoleBinding", role_kind="ClusterRole"):
    return {"binding_kind": kind, "binding_namespace": ns, "binding_name": name,
            "role_kind": role_kind, "role_name": role, "group_name": group}


def ub(name, ns, user, role="edit", platform=0):
    return {"binding_kind": "RoleBinding", "binding_namespace": ns, "binding_name": name,
            "role_kind": "ClusterRole", "role_name": role, "user_name": user, "is_platform": platform}


@pytest.fixture()
def store():
    s = Store(":memory:")
    s.upsert_cluster("crc", "https://api.crc.testing:6443", True)
    yield s
    s.close()


class TestDiff:
    def test_first_observation_is_recorded_and_flagged_baseline(self, store):
        counts = store.replace_bindings("crc", [rb("a", "ns1", "g1"), rb("b", "ns2", "g2")], T1)
        assert counts == {"added": 2, "removed": 0}
        events = store.binding_events("crc")
        assert len(events) == 2 and {e["baseline"] for e in events} == {1}
        assert {e["change"] for e in events} == {"added"}

    def test_an_unchanged_refresh_records_nothing(self, store):
        rows = [rb("a", "ns1", "g1"), rb("b", "ns2", "g2")]
        store.replace_bindings("crc", rows, T1)
        assert store.replace_bindings("crc", list(reversed(rows)), T2) == {"added": 0, "removed": 0}
        assert len(store.binding_events("crc")) == 2

    def test_appearance_and_disappearance_after_baseline_are_real_changes(self, store):
        store.replace_bindings("crc", [rb("a", "ns1", "g1")], T1)
        counts = store.replace_bindings("crc", [rb("b", "ns2", "g2")], T2)
        assert counts == {"added": 1, "removed": 1}
        newest = store.binding_events("crc")[:2]
        assert {(e["binding_name"], e["change"], e["baseline"]) for e in newest} == {
            ("a", "removed", 0), ("b", "added", 0)}

    def test_a_role_change_is_one_removed_and_one_added(self, store):
        store.replace_bindings("crc", [rb("a", "ns1", "g1", role="view")], T1)
        counts = store.replace_bindings("crc", [rb("a", "ns1", "g1", role="admin")], T2)
        assert counts == {"added": 1, "removed": 1}
        newest = [(e["change"], e["role_name"]) for e in store.binding_events("crc")[:2]]
        assert sorted(newest) == [("added", "admin"), ("removed", "view")]

    def test_a_mass_removal_on_an_observed_cluster_is_recorded_as_one(self, store):
        """An empty refresh for a cluster that had rows is a real event — the poller never reaches
        the replace on a fetch failure, so nothing here can mistake a 403 for a wipe."""
        store.replace_bindings("crc", [rb("a", "ns1", "g1"), rb("b", "ns1", "g2")], T1)
        assert store.replace_bindings("crc", [], T2) == {"added": 0, "removed": 2}
        removed = [e for e in store.binding_events("crc") if e["change"] == "removed"]
        assert len(removed) == 2 and all(e["baseline"] == 0 for e in removed)

    def test_user_and_group_subjects_are_independent(self, store):
        store.replace_bindings("crc", [rb("a", "ns1", "g1")], T1)
        # the user side's FIRST observation is its own baseline, even though groups are observed
        counts = store.replace_user_bindings("crc", [ub("u-a", "ns1", "jdoe", role="admin")], T2)
        assert counts == {"added": 1, "removed": 0}
        users = [e for e in store.binding_events("crc") if e["subject_kind"] == "User"]
        assert users[0]["baseline"] == 1 and users[0]["subject_name"] == "jdoe"
        # a later user refresh that drops the row is a real removal, and touches no group row
        assert store.replace_user_bindings("crc", [], T3) == {"added": 0, "removed": 1}
        groups = [e for e in store.binding_events("crc") if e["subject_kind"] == "Group"]
        assert len(groups) == 1

    def test_a_platform_flag_alone_is_not_a_change(self, store):
        """is_platform is metadata on the event, not part of what changed (Cursor, review of #177)."""
        store.replace_user_bindings("crc", [ub("p", "", "svc-x", platform=0)], T1)
        assert store.replace_user_bindings("crc", [ub("p", "", "svc-x", platform=1)], T2) == {"added": 0, "removed": 0}
        assert len(store.binding_events("crc")) == 1

    def test_wipe_then_recreate_is_not_a_second_baseline(self, store):
        """Events of the kind exist after the wipe, so the recreation is a real `added` (Cursor)."""
        store.replace_bindings("crc", [rb("a", "ns1", "g1")], T1)
        store.replace_bindings("crc", [], T2)
        store.replace_bindings("crc", [rb("a", "ns1", "g1")], T3)
        newest = store.binding_events("crc")[0]
        assert (newest["change"], newest["baseline"], newest["observed_at"]) == ("added", 0, T3)

    def test_an_empty_first_binding_refresh_consumes_the_baseline(self, store):
        """Codex, review of #177 (C4): the marker, not the rows, decides the first observation."""
        assert store.replace_bindings("crc", [], T1) == {"added": 0, "removed": 0}
        store.replace_bindings("crc", [rb("a", "ns", "g")], T2)
        assert store.binding_events("crc")[0]["baseline"] == 0

    def test_retention_does_not_reopen_the_baseline(self, store):
        """The marker survives a prune that empties the events (Codex; closes Cursor's accepted debt)."""
        store.replace_bindings("crc", [rb("a", "ns", "g")], T1)
        store.replace_bindings("crc", [], T2)
        assert store.prune_binding_events("crc", T3, max_rows=10) == 2
        assert store.binding_events("crc") == []
        store.replace_bindings("crc", [rb("a", "ns", "g")], T3)
        assert store.binding_events("crc")[0]["baseline"] == 0

    def test_self_scope_does_not_exceed_sqlite_variable_limit(self, store):
        """A viewer in more groups than SQLITE_LIMIT_VARIABLE_NUMBER (Codex, reproduced)."""
        store.replace_bindings("crc", [rb("a", "ns", "g-mine")], T1)
        store._conn.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 16)
        groups = ["g-mine"] + [f"unrelated-{i}" for i in range(20)]
        events = store.binding_events("crc", viewer="alice", viewer_groups=groups)
        assert [(e["subject_kind"], e["subject_name"]) for e in events] == [("Group", "g-mine")]

    def test_groups_polled_without_members_are_still_an_observation(self, tmp_path):
        """Grok, review 2 of #177 (V1): a v13/v14 cluster whose groups were all polled with zero members
        has group_state rows and nothing in group_member / membership_event — the 14 backfill missed it,
        so its first join after the upgrade read as a first observation. The seed at open covers group_state."""
        db = str(tmp_path / "polled-empty.db")
        s = Store(db)
        s.upsert_cluster("crc", "https://api.crc.testing:6443", True)
        s.replace_group_state("crc", [{"name": "g", "member_count": 0, "sync_provider": None,
                                       "group_synced_at": None, "ldap_uid": None, "cliff_silence": None}], T1)
        # rewind to a store a marker-less build wrote to: 14 will not re-run, the open-time seed must
        s._conn.execute("DELETE FROM observation_state")
        s._conn.execute("PRAGMA user_version = 14")
        s._conn.commit(); s.close()
        s = Store(db)
        try:
            assert [r[0] for r in s._conn.execute("SELECT stream FROM observation_state WHERE cluster_id='crc'")] == ["membership"]
            assert s.sync_members("crc", {"g": ["alice"]}, {}, T2) == 1
            event = s.membership_events("crc", user_name="alice")[0]
            assert (event["change"], event["baseline"]) == ("added", 0)
        finally:
            s.close()

    def test_is_platform_rides_the_event(self, store):
        store.replace_user_bindings("crc", [ub("p", "", "system:kube-controller-manager", platform=1)], T1)
        assert store.binding_events("crc")[0]["is_platform"] == 1

    def test_namespace_filter_and_the_empty_string_for_cluster_scope(self, store):
        store.replace_bindings("crc", [rb("a", "ns1", "g1"), rb("c", "", "g3", kind="ClusterRoleBinding")], T1)
        assert [e["binding_name"] for e in store.binding_events("crc", namespace="ns1")] == ["a"]
        assert [e["binding_name"] for e in store.binding_events("crc", namespace="")] == ["c"]

    def test_the_self_slice_is_the_viewer_and_their_groups(self, store):
        store.replace_bindings("crc", [rb("a", "ns1", "g-mine"), rb("b", "ns1", "g-theirs")], T1)
        store.replace_user_bindings("crc", [ub("u", "ns1", "me"), ub("v", "ns1", "someone")], T1)
        mine = store.binding_events("crc", viewer="me", viewer_groups=["g-mine"])
        assert {(e["subject_kind"], e["subject_name"]) for e in mine} == {("Group", "g-mine"), ("User", "me")}
        assert store.binding_events("crc", viewer="me", viewer_groups=[]) and \
            all(e["subject_name"] == "me" for e in store.binding_events("crc", viewer="me", viewer_groups=[]))

    def test_clusters_do_not_bleed(self, store):
        store.upsert_cluster("other", "https://other:6443", True)
        store.replace_bindings("crc", [rb("a", "ns1", "g1")], T1)
        store.replace_bindings("other", [rb("a", "ns1", "g1")], T1)
        assert len(store.binding_events("crc")) == 1 and len(store.binding_events("other")) == 1


class TestRetention:
    def test_prune_is_bounded_by_age_and_batch(self, store):
        now = datetime.now(UTC)
        old = (now - timedelta(days=800)).strftime("%Y-%m-%dT%H:%M:%SZ")
        recent = (now - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        store.replace_bindings("crc", [rb(f"b{i}", "ns", "g") for i in range(30)], old)
        store.replace_bindings("crc", [rb(f"b{i}", "ns", "g") for i in range(30, 40)], recent)  # 30 removed, 10 added
        cutoff = (now - timedelta(days=730)).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert store.prune_binding_events("crc", cutoff, max_rows=20) == 20
        assert store.prune_binding_events("crc", cutoff, max_rows=20) == 10
        assert store.prune_binding_events("crc", cutoff, max_rows=20) == 0
        assert len(store.binding_events("crc", limit=1000)) == 40   # the recent 30 removed + 10 added

    def test_it_is_a_history_table(self, store):
        assert "binding_event" in Store._HISTORY_TABLES
        assert "binding_event" in RETENTION_TABLES
        assert store.history_retained_since("crc")["binding_event"] is None
        store.replace_bindings("crc", [rb("a", "ns", "g")], T1)
        assert store.history_retained_since("crc")["binding_event"] == T1


class TestMetric:
    def test_counts_by_cluster_change_and_kind_and_never_a_name(self):
        signals = RuntimeSignals()
        signals.note_binding_changes("crc", "added", "Group", 3)
        signals.note_binding_changes("crc", "removed", "User", 1)
        signals.note_binding_changes("crc", "added", "User", 0)      # a zero is not an event
        snap = signals.snapshot()["binding_changes"]
        assert snap == {("crc", "added", "Group"): 3, ("crc", "removed", "User"): 1}
        assert set(BINDING_CHANGES) == {"added", "removed"} and set(BINDING_SUBJECT_KINDS) == {"Group", "User"}

    def test_the_family_is_seeded_per_enabled_cluster(self, tmp_path):
        from prometheus_client import generate_latest
        db = str(tmp_path / "gsd.db")
        s = Store(db); s.upsert_cluster("crc", "https://api.crc.testing:6443", True); s.close()
        settings = Settings(clusters=[ClusterConfig(name="crc", api_url="https://api.crc.testing:6443")], db_path=db)
        signals = RuntimeSignals(); signals.note_binding_changes("crc", "added", "Group", 2)
        store = Store(db)
        try:
            text = generate_latest(build_registry(store, timedelta(seconds=120), signals=signals,
                                                  settings=settings)).decode()
        finally:
            store.close()
        assert 'gsd_binding_changes_total{change="added",cluster="crc",subject_kind="Group"} 2.0' in text
        assert 'gsd_binding_changes_total{change="removed",cluster="crc",subject_kind="User"} 0.0' in text
        # no label may carry a name: the only labels are the three bounded ones
        for line in text.splitlines():
            if line.startswith("gsd_binding_changes_total{"):
                labels = line[line.index("{") + 1:line.index("}")]
                assert set(k.split("=")[0] for k in labels.split(",")) == {"change", "cluster", "subject_kind"}


class TestWire:
    @pytest.fixture()
    def client(self, tmp_path):
        db = str(tmp_path / "gsd.db")
        s = Store(db); s.upsert_cluster("crc", "https://api.crc.testing:6443", True)
        s.replace_bindings("crc", [rb("a", "ns1", "g1")], T1)
        s.replace_bindings("crc", [rb("a", "ns1", "g1"), rb("b", "ns2", "g2", role="admin")], T2)
        s.close()
        settings = Settings(clusters=[ClusterConfig(name="crc", api_url="https://api.crc.testing:6443")],
                            db_path=db, membership_events_retention_days=0, view_restrictions_enabled=False)
        with TestClient(build_app(settings, run_poller=False)) as c:
            yield c

    def test_the_envelope(self, client):
        body = client.get("/api/clusters/crc/binding-changes").json()
        assert body["scope"] == "all" and body["count"] == 2 and body["truncated"] is False
        assert body["baseline_rows"] == 1                       # the first observation's row
        assert body["retention"] == {"window_days": 0, "retained_since": T1}
        newest = body["changes"][0]
        assert newest["binding_name"] == "b" and newest["change"] == "added" and newest["baseline"] == 0
        assert body["changes"][1]["baseline"] == 1

    def test_namespace_filter_and_truncation_flag(self, client):
        body = client.get("/api/clusters/crc/binding-changes?namespace=ns2").json()
        assert [c["binding_name"] for c in body["changes"]] == ["b"]
        body = client.get("/api/clusters/crc/binding-changes?limit=1").json()
        assert body["count"] == 1 and body["truncated"] is True

    def test_unknown_cluster_is_a_404(self, client):
        assert client.get("/api/clusters/nope/binding-changes").status_code == 404


class _Resolver:
    """The app.state.tier_resolver seam: viewer -> tier, default self (see tests/test_visibility.py)."""

    def __init__(self, wide: set[str]):
        self.wide = wide

    def resolve(self, viewer: str) -> str:
        return "all" if viewer in self.wide else "self"


class TestSelfTier:
    @pytest.fixture()
    def client(self, tmp_path):
        db = str(tmp_path / "gsd.db")
        s = Store(db); s.upsert_cluster("crc", "https://api.crc.testing:6443", True)
        s.sync_members("crc", {"g-mine": ["alice"], "g-theirs": ["bob"]}, {}, T1)
        s.replace_bindings("crc", [rb("a", "ns1", "g-mine"), rb("b", "ns1", "g-theirs")], T1)
        s.replace_user_bindings("crc", [ub("u", "ns1", "alice"), ub("v", "ns1", "someone")], T1)
        s.close()
        settings = Settings(clusters=[ClusterConfig(name="crc", api_url="https://api.crc.testing:6443")],
                            db_path=db, view_restrictions_enabled=True, oauth_proxy_enabled=True)
        app = build_app(settings, run_poller=False)
        app.state.tier_resolver = _Resolver({"root"})
        with TestClient(app) as c:
            yield c

    def test_a_narrowed_viewer_sees_only_their_own_slice(self, client):
        body = client.get("/api/clusters/crc/binding-changes", headers={"X-Forwarded-User": "alice"}).json()
        assert body["scope"] == "self" and body["viewer"] == "alice"
        assert {(c["subject_kind"], c["subject_name"]) for c in body["changes"]} == {
            ("Group", "g-mine"), ("User", "alice")}

    def test_the_wide_tier_sees_everything(self, client):
        body = client.get("/api/clusters/crc/binding-changes", headers={"X-Forwarded-User": "root"}).json()
        assert body["scope"] == "all" and body["count"] == 4

    def test_no_viewer_behind_the_proxy_is_refused_not_widened(self, client):
        assert client.get("/api/clusters/crc/binding-changes").status_code in (401, 403)


class TestUpgrade:
    def test_a_v12_membership_event_table_gains_baseline_and_keeps_working(self, tmp_path):
        """The class of bug test_migrations.py exists for: on an EXISTING database the SCHEMA's
        `baseline` column never appears by itself, so migration 13's ALTER must add it — and the
        first sync_members afterwards must not crash naming a column that is not there (Cursor)."""
        import sqlite3
        db = str(tmp_path / "v12.db")
        conn = sqlite3.connect(db)
        conn.executescript("""
            CREATE TABLE membership_event (
                id INTEGER PRIMARY KEY AUTOINCREMENT, cluster_id TEXT NOT NULL, group_name TEXT NOT NULL,
                user_name TEXT NOT NULL, change TEXT NOT NULL, observed_at TEXT NOT NULL, group_synced_at TEXT);
            INSERT INTO membership_event(cluster_id, group_name, user_name, change, observed_at)
                VALUES('crc', 'g', 'alice', 'added', '2026-08-02T04:00:33Z');
            PRAGMA user_version = 12;
        """)
        conn.commit(); conn.close()
        store = Store(db)
        try:
            cols = {r[1] for r in store._conn.execute("PRAGMA table_info(membership_event)")}
            assert "baseline" in cols
            assert store._conn.execute("PRAGMA user_version").fetchone()[0] == 15
            assert store._conn.execute("SELECT baseline FROM membership_event").fetchone()[0] == 0
            store.upsert_cluster("crc", "https://api.crc.testing:6443", True)
            # events already exist for crc, so this is NOT a first observation
            assert store.sync_members("crc", {"g": ["alice", "bob"]}, {}, T1) == 2
            assert store.membership_events("crc", user_name="bob")[0]["baseline"] == 0
        finally:
            store.close()


def test_self_scope_with_groups_seeks_the_subject_index_for_both_halves(monkeypatch):
    """OB1, review 2 of #177 (S6d): without statistics (this store never runs ANALYZE) the OR form
    walked every row of the cluster and sorted — measured 306 ms at 300k rows against 1.8 ms for two
    index seeks. Fails on the OR form with the by_time plan; passes on the UNION ALL form."""
    store = Store(":memory:")
    store.upsert_cluster("crc", "https://api.crc.testing:6443", True)
    captured: dict = {}
    orig = Store._rows

    def spy(self, sql, params=()):
        captured.update(sql=sql, params=list(params))
        return orig(self, sql, params)
    monkeypatch.setattr(Store, "_rows", spy)

    def plan_of(**kw):
        store.binding_events("crc", **kw)
        return " | ".join(r[3] for r in store._conn.execute("EXPLAIN QUERY PLAN " + captured["sql"], captured["params"]))
    try:
        store.replace_bindings("crc", [rb("a", "ns", "g-mine")], T1)
        plan = plan_of(viewer="alice", viewer_groups=["g-mine", "g-other"])
        assert plan.count("USING INDEX binding_event_by_subject") == 2, plan
        assert "binding_event_by_time" not in plan, plan
        plan = plan_of(namespace="ns", viewer="alice", viewer_groups=["g-mine"])
        assert "binding_event_by_time" not in plan, plan
    finally:
        store.close()
