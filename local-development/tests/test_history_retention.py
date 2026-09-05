"""Retention on the two tables the backup exists for.

The claims, each with its test: pruned by age; bounded per call; nothing on a non-positive
limit; leader-only; after the backup and never before one has succeeded; counted into the
metric from the same number; both defaults, in the app and in the chart; and the wire says
where the cut is.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
from datetime import UTC, datetime, timedelta

import pytest
import yaml
from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.config import ClusterConfig, Settings, load_settings
from gsd.metrics import RETENTION_TABLES, RuntimeSignals
from gsd.poller import HISTORY_PRUNE_BATCH, Poller
from gsd.store import Store

REPO = pathlib.Path(__file__).resolve().parents[2]
CHART = REPO / "charts" / "group-sync-dashboard"
INDEX = REPO / "local-development" / "gsd" / "static" / "index.html"
CLUSTER = ClusterConfig(name="crc", api_url="https://api.crc.testing:6443", token_env="X")


# One clock for the whole module: a test that seeds rows and then recomputes "now" after the app
# has started can straddle a second boundary and compare two different seconds (seen in review).
NOW = datetime.now(UTC)


def _iso(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _seed(store: Store, table: str, n: int, days_ago: float, cluster: str = "crc") -> None:
    """Rows straight into the table: the poller's own writes stamp now_iso() and cannot be
    back-dated through the public methods."""
    with store._write() as conn:
        if table == "membership_event":
            conn.executemany(
                """INSERT INTO membership_event(cluster_id, group_name, user_name, change,
                       observed_at, group_synced_at) VALUES(?,?,?,'added',?,NULL)""",
                [(cluster, "g", f"u{i}", _iso(days_ago + i / 86400)) for i in range(n)],
            )
        else:
            conn.executemany(
                """INSERT INTO sync_event(cluster_id, groupsync_name, groupsync_namespace,
                       synced_at, observed_at, schedule, group_count) VALUES(?,?,?,?,?,?,?)""",
                [(cluster, "corp", "ns", f"{_iso(days_ago + i / 86400)}", _iso(days_ago + i / 86400),
                  "0 * * * *", 1) for i in range(n)],
            )


def _count(store: Store, table: str, cluster: str = "crc") -> int:
    return store._rows(f"SELECT COUNT(*) AS n FROM {table} WHERE cluster_id=?", (cluster,))[0]["n"]


@pytest.fixture()
def store(tmp_path):
    s = Store(str(tmp_path / "gsd.db"))
    s.upsert_cluster("crc", "https://api.crc.testing:6443", True)
    s.upsert_cluster("other", "https://api.other:6443", True)
    yield s
    s.close()


class _Elector:
    def __init__(self, leader: bool):
        self.is_leader = leader


class TestStorePrune:
    @pytest.mark.parametrize("table,prune", [
        ("membership_event", "prune_membership_events"), ("sync_event", "prune_sync_events")])
    def test_prunes_by_age_and_leaves_the_rest(self, store, table, prune):
        _seed(store, table, 10, days_ago=800)
        _seed(store, table, 10, days_ago=10)
        _seed(store, table, 5, days_ago=800, cluster="other")
        removed = getattr(store, prune)("crc", _iso(730))
        assert removed == 10
        assert _count(store, table) == 10
        assert _count(store, table, "other") == 5, "another cluster's rows were touched"

    @pytest.mark.parametrize("table,prune", [
        ("membership_event", "prune_membership_events"), ("sync_event", "prune_sync_events")])
    def test_each_call_is_bounded_and_the_backlog_drains_across_calls(self, store, table, prune):
        _seed(store, table, 12_000, days_ago=800)
        cutoff = _iso(730)
        assert getattr(store, prune)("crc", cutoff) == 5000
        assert getattr(store, prune)("crc", cutoff) == 5000
        assert getattr(store, prune)("crc", cutoff) == 2000
        assert getattr(store, prune)("crc", cutoff) == 0

    def test_a_non_positive_limit_deletes_nothing(self, store):
        """SQLite reads LIMIT -1 as unlimited — the opposite of the contract."""
        _seed(store, "membership_event", 10, days_ago=800)
        assert store.prune_membership_events("crc", _iso(730), max_rows=0) == 0
        assert store.prune_membership_events("crc", _iso(730), max_rows=-1) == 0
        assert _count(store, "membership_event") == 10

    def test_retained_since_is_the_oldest_row_left(self, store):
        _seed(store, "membership_event", 3, days_ago=800)
        _seed(store, "membership_event", 1, days_ago=100)
        # _seed spaces its rows one second apart, so the OLDEST of three is two seconds older.
        assert store.history_retained_since("crc")["membership_event"] == _iso(800 + 2 / 86400)
        store.prune_membership_events("crc", _iso(730))
        assert store.history_retained_since("crc")["membership_event"] == _iso(100)
        assert store.history_retained_since("other") == {"membership_event": None, "sync_event": None}

    def test_the_shared_index_comment_does_not_deny_retention(self):
        """B4 wrote 'the table has no retention by design' above the index B2 now prunes through."""
        src = (pathlib.Path(__file__).resolve().parents[1] / "gsd" / "store.py").read_text()
        start = src.index("CREATE INDEX IF NOT EXISTS membership_event_by_time")
        comment = src[max(0, start - 500):start]
        assert "no retention by design" not in comment
        assert "retention" in comment.lower()

    def test_the_retention_indexes_exist(self, store):
        names = {r["name"] for r in store._rows("SELECT name FROM sqlite_master WHERE type='index'")}
        assert {"membership_event_by_time", "sync_event_by_time"} <= names


class _Recording(Store):
    """A Store that records the order of its upkeep calls."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.calls: list[str] = []

    def maintain(self):
        self.calls.append("maintain")
        return super().maintain()

    def backup(self, directory, keep=3):
        self.calls.append("backup")
        return super().backup(directory, keep)

    def prune_membership_events(self, cluster_id, before_at, max_rows=5000):
        self.calls.append("prune_membership_events")
        return super().prune_membership_events(cluster_id, before_at, max_rows)

    def prune_sync_events(self, cluster_id, before_at, max_rows=5000):
        self.calls.append("prune_sync_events")
        return super().prune_sync_events(cluster_id, before_at, max_rows)


@pytest.fixture()
def recording(tmp_path):
    s = _Recording(str(tmp_path / "gsd.db"))
    s.upsert_cluster("crc", "https://api.crc.testing:6443", True)
    yield s
    s.close()


def _settings(tmp_path, **overrides) -> Settings:
    base = dict(clusters=[CLUSTER], db_path=str(tmp_path / "gsd.db"),
                backup_dir=str(tmp_path / "backup"),
                membership_events_retention_days=365, sync_events_retention_days=365)
    base.update(overrides)
    return Settings(**base)


class TestPollerPrune:
    def test_order_is_maintain_backup_then_prune(self, recording, tmp_path):
        poller = Poller(recording, _settings(tmp_path))
        poller._after_poll(CLUSTER)
        assert recording.calls == ["maintain", "backup", "prune_membership_events", "prune_sync_events"]

    def test_nothing_is_deleted_until_a_backup_has_succeeded(self, recording, tmp_path):
        """A failing backup HOLDS the prune; the first good one releases it."""
        _seed(recording, "membership_event", 5, days_ago=800)
        poller = Poller(recording, _settings(tmp_path, backup_dir="/proc/nonexistent-and-unwritable"))
        poller._after_poll(CLUSTER)
        assert "prune_membership_events" not in recording.calls
        assert _count(recording, "membership_event") == 5
        poller.settings = _settings(tmp_path)          # backups now work
        poller._next_backup = 0.0
        poller._after_poll(CLUSTER)
        assert _count(recording, "membership_event") == 0

    def test_with_backups_disabled_retention_is_held(self, recording, tmp_path):
        """Nothing is ever deleted when config.backup is off: the history would have no copy
        anywhere. Modelled as derive, not refuse, in the #69 review (the operator's 730 default stands)."""
        _seed(recording, "sync_event", 5, days_ago=800)
        Poller(recording, _settings(tmp_path, backup_dir=""))._after_poll(CLUSTER)
        assert "backup" not in recording.calls
        assert not [c for c in recording.calls if c.startswith("prune")]
        assert _count(recording, "sync_event") == 5

    def test_a_standby_does_not_prune(self, recording, tmp_path):
        _seed(recording, "membership_event", 5, days_ago=800)
        poller = Poller(recording, _settings(tmp_path), elector=_Elector(leader=False))
        poller._backup_state = "ok"                     # the gate under test is leadership
        poller._prune_history(CLUSTER)
        assert _count(recording, "membership_event") == 5

    def test_leadership_lost_between_the_gate_and_the_write_stops_the_prune(self, recording, tmp_path):
        """Leader at the outer gate, standby by the time the first table would be deleted: the
        per-table re-check catches it (review, PR #73). Best-effort, not a fencing token."""
        class _LosingElector:
            def __init__(self):
                self._states = iter((True, False))
            @property
            def is_leader(self) -> bool:
                return next(self._states, False)
        _seed(recording, "membership_event", 5, days_ago=800)
        poller = Poller(recording, _settings(tmp_path), elector=_LosingElector())
        poller._backup_state = "ok"
        poller._prune_history(CLUSTER)
        assert not [c for c in recording.calls if c.startswith("prune")]
        assert _count(recording, "membership_event") == 5

    def test_membership_prune_does_not_cut_inside_the_cliff_window(self, recording, tmp_path):
        """A 1-day membership window with a 48h cliff: a drop 30h ago must still be visible to
        group_count_changes after the prune, or GroupSyncGroupCountCliff goes silent (review, PR #73)."""
        def _at(hours_ago: float) -> str:
            return (datetime.now(UTC) - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with recording._write() as conn:
            conn.executemany(
                """INSERT INTO membership_event(cluster_id, group_name, user_name, change,
                       observed_at, group_synced_at) VALUES(?,?,?,'removed',?,NULL)""",
                [("crc", "g", f"u{i}", _at(30 + i / 3600)) for i in range(12)]
                + [("crc", "g", f"old{i}", _at(80 + i / 3600)) for i in range(5)],
            )
        poller = Poller(recording, _settings(tmp_path, membership_events_retention_days=1,
                                              sync_events_retention_days=0,
                                              group_count_cliff_enabled=True,
                                              group_count_cliff_window_hours=48.0))
        poller._after_poll(CLUSTER)
        inside = recording.group_count_changes("crc", _at(48))
        assert inside.get("g", {}).get("removed") == 12, f"the cliff window went blind: {inside!r}"
        assert _count(recording, "membership_event") == 12, "rows older than both edges must still go"

    def test_a_user_whose_only_rows_were_pruned_is_unknown(self, tmp_path):
        """Preservation, labelled: no tombstone (it would be a username oracle), so the 404 is what
        the store can still say, and the page never receives `retention` — hence the README sentence."""
        db = str(tmp_path / "gsd.db")
        s = Store(db)
        s.upsert_cluster("crc", "https://api.crc.testing:6443", True)
        with s._write() as conn:
            conn.execute("""INSERT INTO membership_event(cluster_id, group_name, user_name, change,
                                observed_at, group_synced_at) VALUES(?,?,?,'removed',?,NULL)""",
                         ("crc", "g", "ghost", _iso(800)))
        s.prune_membership_events("crc", _iso(730))
        s.close()
        settings = Settings(clusters=[CLUSTER], db_path=db, membership_events_retention_days=365,
                            sync_events_retention_days=0, view_restrictions_enabled=False)
        with TestClient(build_app(settings, run_poller=False)) as c:
            r = c.get("/api/clusters/crc/users/ghost")
            assert r.status_code == 404 and "retention" not in r.json()

    def test_zero_keeps_everything_and_calls_nothing(self, recording, tmp_path):
        _seed(recording, "membership_event", 5, days_ago=5000)
        _seed(recording, "sync_event", 5, days_ago=5000)
        poller = Poller(recording, _settings(tmp_path, membership_events_retention_days=0,
                                              sync_events_retention_days=0))
        poller._after_poll(CLUSTER)
        assert not [c for c in recording.calls if c.startswith("prune")]
        assert _count(recording, "membership_event") == 5 and _count(recording, "sync_event") == 5

    def test_a_table_at_zero_is_untouched_while_the_other_prunes(self, recording, tmp_path):
        _seed(recording, "membership_event", 5, days_ago=5000)
        _seed(recording, "sync_event", 5, days_ago=5000)
        Poller(recording, _settings(tmp_path, membership_events_retention_days=0))._after_poll(CLUSTER)
        assert _count(recording, "membership_event") == 5 and _count(recording, "sync_event") == 0

    def test_deletions_reach_the_metric_by_table_and_stay_bounded(self, recording, tmp_path):
        _seed(recording, "membership_event", HISTORY_PRUNE_BATCH + 7, days_ago=800)
        _seed(recording, "sync_event", 3, days_ago=800)
        signals = RuntimeSignals()
        poller = Poller(recording, _settings(tmp_path), signals=signals)
        poller._after_poll(CLUSTER)
        snap = signals.snapshot()["retention"]
        assert snap == {"membership_event": HISTORY_PRUNE_BATCH, "sync_event": 3}
        poller._after_poll(CLUSTER)
        assert signals.snapshot()["retention"]["membership_event"] == HISTORY_PRUNE_BATCH + 7

    def test_the_metric_family_declares_both_tables(self):
        assert {"membership_event", "sync_event"} <= set(RETENTION_TABLES)


class TestDefaults:
    def test_the_app_defaults(self):
        s = Settings()
        assert s.membership_events_retention_days == 0
        assert s.sync_events_retention_days == 730

    def test_the_configmap_keys_and_env_are_read(self, tmp_path, monkeypatch):
        p = tmp_path / "clusters.yaml"
        p.write_text("clusters:\n  - name: crc\n    apiUrl: https://api.crc.testing:6443\n"
                     "    tokenEnv: X\nmembershipEventsRetentionDays: 30\nsyncEventsRetentionDays: 0\n")
        s = load_settings(str(p))
        assert (s.membership_events_retention_days, s.sync_events_retention_days) == (30, 0)
        monkeypatch.setenv("GSD_SYNC_EVENTS_RETENTION_DAYS", "90")
        assert load_settings(str(p)).sync_events_retention_days == 90

    def test_operator_docs_say_to_zero_the_windows_before_a_restore(self):
        """B1's runbook is not in this release; a restoring operator has the chart README and the
        changelog, and the first successful backup of a new process releases the prune (review, PR #73)."""
        section = (CHART / "README.md").read_text().split("### Retention on the history")[1].split("\n### ")[0]
        assert "set both windows to `0`" in section and "restore" in section.lower()
        assert "set both windows to" in (REPO / "docs" / "CHANGELOG.md").read_text()

    @pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")
    def test_the_chart_defaults_equal_the_app_defaults(self):
        """Two sources of one number; the environments README test applies the same rule."""
        done = subprocess.run(["helm", "template", "t", str(CHART), "--set", "ingress.host=t.example.com"],
                              capture_output=True, text=True)
        assert done.returncode == 0, done.stderr
        cm = [d for d in yaml.safe_load_all(done.stdout)
              if d and d.get("kind") == "ConfigMap" and d["metadata"]["name"].endswith("-config")][0]
        raw = yaml.safe_load(cm["data"]["clusters.yaml"])
        assert raw["membershipEventsRetentionDays"] == Settings().membership_events_retention_days
        assert raw["syncEventsRetentionDays"] == Settings().sync_events_retention_days


@pytest.fixture()
def client(tmp_path):
    db = str(tmp_path / "gsd.db")
    s = Store(db)
    s.upsert_cluster("crc", "https://api.crc.testing:6443", True)
    s.record_sync_event("crc", "corp", "ns", "2026-08-02T09:00:00Z", "2026-08-02T09:00:30Z", "0 * * * *", 4)
    _seed(s, "membership_event", 2, days_ago=100)
    s.close()
    settings = Settings(clusters=[ClusterConfig(name="crc", api_url="https://api.crc.testing:6443")],
                        db_path=db, membership_events_retention_days=0, sync_events_retention_days=730,
                        view_restrictions_enabled=False)
    with TestClient(build_app(settings, run_poller=False)) as c:
        yield c


class TestWire:
    def test_events_say_the_sync_window_and_edge(self, client):
        body = client.get("/api/clusters/crc/groupsyncs/corp/events").json()
        assert body["retention"] == {"window_days": 730, "retained_since": "2026-08-02T09:00:30Z"}

    def test_membership_changes_say_forever_and_the_oldest_row(self, client):
        body = client.get("/api/clusters/crc/membership-changes").json()
        assert body["retention"]["window_days"] == 0
        assert body["retention"]["retained_since"] == _iso(100 + 1 / 86400)

    def test_group_and_user_pages_carry_it_too(self, client):
        assert "retention" in client.get("/api/clusters/crc/groups/g").json()
        assert "retention" in client.get("/api/clusters/crc/users/u0").json()

    def test_an_unknown_cluster_is_still_a_404(self, client):
        assert client.get("/api/clusters/nope/membership-changes").status_code == 404

    def test_empty_history_copy_does_not_say_yet_when_a_window_is_on(self):
        """'No changes yet' beside a retention cut is the false absence retention exists to stop."""
        html = INDEX.read_text()
        hist = html[html.index("<h2>History</h2>"):html.index("<h2>History</h2>") + 1200]
        assert "window_days" in hist and "retained window" in hist
        grp = html[html.index("const changeBody = changes.length"):]
        grp = grp[:grp.index("return `<section")]
        assert "window_days" in grp and "retained window" in grp

    def test_operator_docs_say_what_a_membership_window_costs(self):
        section = (CHART / "README.md").read_text().split("### Retention on the history")[1].split("\n### ")[0]
        assert "404" in section and "earlier of the two edges" in section

    def test_the_page_renders_the_cut(self):
        html = INDEX.read_text()
        assert "function retentionNote(r)" in html
        assert "History retained since" in html
        assert html.count("retentionNote(") >= 4, "the CR, group and user pages must all say it"
