"""The KPI module (#156): one definition, two renderers, a privacy class that is enforced, a cgroup
sampler that omits what it cannot measure, counters that retention cannot move backwards, a daily
rollup the leader writes once, and predicates the compliance snapshot shares."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry, generate_latest

from gsd.api import build_app
from gsd.kpi import COMPONENTS, INTERNAL, PUBLIC, Context, Kpi, Sample
from gsd.kpi import definitions as defs
from gsd.kpi import rollup
from gsd.kpi.predicates import GROUP_EMPTY, GROUP_UNATTRIBUTED
from gsd.kpi.render_json import page_payload, render as render_json
from gsd.kpi.render_prom import PrivacyViolation, render as render_prom
from gsd.kpi.system import CgroupSampler, Cpu, SystemMonitor, cpu_rate, disk
from gsd.metrics import RETENTION_TABLES, RuntimeSignals, build_registry
from gsd.reporting.snapshot import Snapshot
from gsd.store import Store
from reporting_seed import CLUSTER, NOW, seed_store, write_snapshot
from test_visibility import H, _MapResolver, _seed, _settings

GRACE = timedelta(seconds=120)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _series(text: str, name: str) -> dict[str, float]:
    out = {}
    for line in text.splitlines():
        if line.startswith("#") or not line.startswith(name):
            continue
        metric, _, value = line.rpartition(" ")
        out[metric] = float(value)
    return out


def _scrape(store: Store, signals: RuntimeSignals | None = None, **kw) -> str:
    return generate_latest(build_registry(store, GRACE, signals=signals, **kw)).decode()


# ── the definitions and the privacy class ─────────────────────────────────────────────────

class TestDefinitions:
    def test_every_definition_carries_a_privacy_class_and_bounded_labels(self):
        assert defs.ALL_KPIS == defs.PUBLIC_KPIS + defs.INTERNAL_KPIS
        for kpi in defs.ALL_KPIS:
            assert kpi.privacy in (PUBLIC, INTERNAL), kpi.name
            # No public label may ever be a name: the /metrics rule, pinned on the definitions.
            assert not ({"user", "user_name", "group", "group_name", "name"} & set(kpi.labels)), kpi.name
        assert {k.name for k in defs.PUBLIC_KPIS} == {
            "gsd_process_memory_bytes", "gsd_process_memory_limit_bytes",
            "gsd_process_cpu_usage_seconds_total", "gsd_process_cpu_limit_cores",
            "gsd_process_cpu_periods_total", "gsd_process_cpu_throttled_periods_total",
            "gsd_process_cpu_throttled_seconds_total",
            "gsd_volume_disk_used_bytes", "gsd_volume_disk_total_bytes",
            "gsd_membership_changes_total", "gsd_login_attempts_total",
        }

    def test_people_counts_are_internal(self):
        """The gsd_dashboard_active_users ruling: a count of people is personnel information on an
        unauthenticated endpoint, however unlabelled. Pinned on the class, not on a name."""
        people = {k.name: k.privacy for k in defs.ALL_KPIS if k.name in ("users_total", "members_total")}
        assert people == {"users_total": INTERNAL, "members_total": INTERNAL}

    def test_a_definition_rejects_an_unknown_class_or_kind(self):
        with pytest.raises(ValueError):
            Kpi("x", "h", "gauge", (), "secret", lambda ctx: None)
        with pytest.raises(ValueError):
            Kpi("x", "h", "histogram", (), PUBLIC, lambda ctx: None)

    def test_the_prometheus_renderer_refuses_an_internal_definition(self):
        """Enforced by the renderer, not by which tuple a caller passes: the whole exposition is
        refused before any family is built."""
        with pytest.raises(PrivacyViolation, match="users_total"):
            list(render_prom(defs.ALL_KPIS, Context(component="dashboard")))

    def test_no_internal_definition_reaches_metrics_on_the_real_app(self, tmp_path):
        db = str(tmp_path / "gsd.db")
        _seed(db)
        app = build_app(_settings(db), run_poller=False)
        with TestClient(app) as client:
            text = client.get("/metrics").text
        for kpi in defs.INTERNAL_KPIS:
            assert kpi.name not in text, kpi.name
        for kpi in defs.PUBLIC_KPIS:
            assert f"# HELP {kpi.name} " in text, f"{kpi.name} must be declared even when unmeasured"

    def test_the_component_label_is_one_of_two_values(self, tmp_path):
        sampler = _sampler(tmp_path)
        for component in COMPONENTS:
            families = list(render_prom(defs.PUBLIC_KPIS, Context(component=component, system=sampler)))
            values = {s.labels["component"] for f in families for s in f.samples if "component" in s.labels}
            assert values == {component}
        assert COMPONENTS == ("dashboard", "report")


# ── the cgroup sampler ───────────────────────────────────────────────────────────────────

def _sampler(tmp_path: Path, *, memory_max="536870912", cpu_max="50000 100000",
             usage_usec=5058284, nr_periods=175931, nr_throttled=196, throttled_usec=5058284) -> CgroupSampler:
    """Synthetic cgroup v2 files with the values measured on the reference dashboard pod (#156)."""
    root = tmp_path / "cgroup"
    root.mkdir(exist_ok=True)
    (root / "cgroup.controllers").write_text("cpuset cpu io memory pids\n")
    (root / "memory.current").write_text("105410560\n")
    (root / "memory.max").write_text(f"{memory_max}\n")
    (root / "cpu.max").write_text(f"{cpu_max}\n")
    (root / "cpu.stat").write_text(
        f"usage_usec {usage_usec}\nuser_usec 4000000\nsystem_usec 1058284\n"
        f"nr_periods {nr_periods}\nnr_throttled {nr_throttled}\nthrottled_usec {throttled_usec}\n")
    return CgroupSampler(str(root))


class TestCgroupSampler:
    def test_reads_the_measured_v2_shape(self, tmp_path):
        s = _sampler(tmp_path)
        m, c = s.memory(), s.cpu()
        assert (m.current_bytes, m.limit_bytes) == (105410560, 536870912)
        assert c.limit_cores == 0.5
        assert c.usage_seconds == pytest.approx(5.058284)
        assert (c.periods, c.throttled_periods) == (175931, 196)
        assert c.throttled_seconds == pytest.approx(5.058284)

    def test_unlimited_is_none_never_zero(self, tmp_path):
        s = _sampler(tmp_path, memory_max="max", cpu_max="max 100000")
        assert s.memory().limit_bytes is None
        assert s.cpu().limit_cores is None
        families = {f.name: f for f in render_prom(defs.PUBLIC_KPIS, Context(component="dashboard", system=s))}
        assert families["gsd_process_memory_limit_bytes"].samples == []
        assert families["gsd_process_cpu_limit_cores"].samples == []
        assert families["gsd_process_memory_bytes"].samples[0].value == 105410560

    def test_cgroup_v1_or_absent_is_omitted(self, tmp_path):
        s = CgroupSampler(str(tmp_path / "v1"))          # no cgroup.controllers: v1 or not mounted
        assert not s.available and s.memory() is None and s.cpu() is None
        families = {f.name: f for f in render_prom(defs.PUBLIC_KPIS, Context(component="dashboard", system=s))}
        assert all(families[n].samples == [] for n in families if n.startswith("gsd_process_"))
        assert "gsd_process_memory_bytes" in families, "declared, unsampled"

    def test_a_garbled_file_is_omitted_not_zero(self, tmp_path):
        s = _sampler(tmp_path)
        (tmp_path / "cgroup" / "cpu.max").write_text("what\n")
        assert s.cpu() is None
        assert s.memory() is not None

    def test_the_rate_uses_the_monotonic_clock_and_cannot_go_negative(self):
        a = Cpu(usage_seconds=10.0, limit_cores=0.5, periods=100, throttled_periods=1, throttled_seconds=0.1, monotonic=1000.0)
        b = Cpu(usage_seconds=12.5, limit_cores=0.5, periods=150, throttled_periods=6, throttled_seconds=0.6, monotonic=1010.0)
        r = cpu_rate(a, b)
        assert r.cores_used == pytest.approx(0.25) and r.throttled_fraction == pytest.approx(0.1)
        assert r.interval_seconds == 10.0
        assert cpu_rate(None, b) is None
        assert cpu_rate(b, a) is None, "a non-advancing monotonic clock yields no rate"
        wrapped = Cpu(usage_seconds=1.0, limit_cores=0.5, periods=150, throttled_periods=6, throttled_seconds=0.6, monotonic=1020.0)
        assert cpu_rate(b, wrapped).cores_used == 0.0

    def test_the_monitor_view_carries_a_rate_from_the_second_sample(self, tmp_path):
        s = _sampler(tmp_path)
        mon = SystemMonitor(s, str(tmp_path), min_rate_interval=0.0)
        first = mon.view()
        assert first["cpu"]["cores_used"] is None and first["memory"]["limit_bytes"] == 536870912
        assert first["disk"]["total_bytes"] > 0
        _sampler(tmp_path, usage_usec=6058284, nr_periods=175941, nr_throttled=198)
        second = mon.view()
        assert second["cpu"]["cores_used"] is not None and second["cpu"]["throttled_fraction"] == pytest.approx(0.2)
        assert SystemMonitor(CgroupSampler(str(tmp_path / "none")), None).view() is None

    def test_a_rate_is_never_minted_over_a_sliver(self, tmp_path, monkeypatch):
        """Measured on CRC: the two cluster threads pulled the report's usage feed milliseconds apart and
        the second view said cores_used 0.0813 over rate_interval_seconds 0.0. Inside the minimum
        interval a view repeats the last rate (None until one exists); the baseline does not move."""
        clock = {"t": 1000.0}
        monkeypatch.setattr("gsd.kpi.system.time.monotonic", lambda: clock["t"])
        s = _sampler(tmp_path)
        mon = SystemMonitor(s, None, min_rate_interval=5.0)
        assert mon.view()["cpu"]["cores_used"] is None
        clock["t"] += 0.01
        _sampler(tmp_path, usage_usec=5158284)
        assert mon.view()["cpu"]["rate_interval_seconds"] is None, "10 ms is not an interval"
        clock["t"] += 10.0
        _sampler(tmp_path, usage_usec=6058284, nr_periods=175941, nr_throttled=198)
        view = mon.view()
        assert view["cpu"]["rate_interval_seconds"] == pytest.approx(10.0, abs=0.1)
        assert view["cpu"]["cores_used"] == pytest.approx(1.0 / 10.01, abs=0.01)
        clock["t"] += 1.0
        again = mon.view()
        assert again["cpu"] == view["cpu"] | {"usage_seconds": again["cpu"]["usage_seconds"]}, "the last rate, repeated"

    def test_the_poller_takes_a_baseline_once_a_cycle(self, tmp_path):
        from gsd.config import ClusterConfig
        from gsd.poller import Poller

        class Monitor:
            views = 0
            def view(self):
                self.views += 1

        store = seed_store(str(tmp_path / "w.db"))
        try:
            mon = Monitor()
            poller = Poller(store, _settings(str(tmp_path / "w.db")), signals=None, system_monitor=mon)
            poller._after_poll(ClusterConfig(CLUSTER, "https://x", token_env="T"))
        finally:
            store.close()
        assert mon.views == 1

    def test_disk_is_statvfs_of_the_path(self, tmp_path):
        d = disk(str(tmp_path))
        assert d is not None and 0 < d.used_bytes <= d.total_bytes
        assert disk(str(tmp_path / "missing")) is None


# ── the counters: accumulated under a watermark, retention-proof ──────────────────────────

def _churn_store() -> Store:
    now = datetime.now(UTC)
    store = Store(":memory:")
    store.upsert_cluster("crc", "https://x", True)
    store.record_poll("crc", "ok", None)
    # First observation: baseline rows, not churn.
    store.sync_members("crc", {"g": ["a", "b"]}, {}, _iso(now - timedelta(days=40)))
    # A change 20 days ago and one today.
    store.sync_members("crc", {"g": ["a"]}, {}, _iso(now - timedelta(days=20)))
    store.sync_members("crc", {"g": ["a", "c"]}, {}, _iso(now))
    return store


class TestWatermarkCounters:
    def test_membership_changes_exclude_the_baseline_and_survive_retention(self):
        store = _churn_store()
        signals = RuntimeSignals()
        text = _scrape(store, signals)
        assert _series(text, "gsd_membership_changes_total") == {
            'gsd_membership_changes_total{change="added",cluster="crc"}': 1.0,
            'gsd_membership_changes_total{change="removed",cluster="crc"}': 1.0,
        }
        # Retention removes the old rows; the counter does not move.
        assert store.prune_membership_events("crc", _iso(datetime.now(UTC) - timedelta(days=10))) == 3
        assert _series(_scrape(store, signals), "gsd_membership_changes_total")[
            'gsd_membership_changes_total{change="removed",cluster="crc"}'] == 1.0
        # A new change is counted once, however many scrapes follow.
        store.sync_members("crc", {"g": ["a"]}, {}, _iso(datetime.now(UTC)))
        for _ in range(3):
            removed = _series(_scrape(store, signals), "gsd_membership_changes_total")[
                'gsd_membership_changes_total{change="removed",cluster="crc"}']
        assert removed == 2.0

    def test_login_attempts_by_outcome_and_provider_preseeded(self):
        store = Store(":memory:")
        store.upsert_cluster("crc", "https://x", True)
        store.record_poll("crc", "ok", None)
        at = datetime.now(UTC)
        store.record_login_events("crc", [
            {"pod_name": "p", "user_name": u, "outcome": o, "at": (at - timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
             "provider": prov, "ldap_result_code": None, "detail": None, "observed_at": _iso(at)}
            for i, (u, o, prov) in enumerate([("alice", "success", "ldap"), ("bob", "bad_password", "ldap"),
                                              ("ghost", "rejected", None)])
        ])
        signals = RuntimeSignals()
        s = _series(_scrape(store, signals), "gsd_login_attempts_total")
        assert s['gsd_login_attempts_total{cluster="crc",outcome="success",provider="ldap"}'] == 1.0
        assert s['gsd_login_attempts_total{cluster="crc",outcome="bad_password",provider="ldap"}'] == 1.0
        assert s['gsd_login_attempts_total{cluster="crc",outcome="rejected",provider="unknown"}'] == 1.0
        # Every outcome the parser can decide is pre-seeded under each provider seen.
        assert s['gsd_login_attempts_total{cluster="crc",outcome="account_locked",provider="ldap"}'] == 0.0
        assert len(s) == len(defs.LOGIN_OUTCOMES) * 2
        assert not any("alice" in k or "bob" in k or "ghost" in k for k in s)

    def test_unwired_signals_declare_the_families_and_sample_nothing(self):
        text = _scrape(_churn_store())
        assert "# HELP gsd_membership_changes_total " in text
        assert _series(text, "gsd_membership_changes_total") == {}


# ── the trends and the shared predicates ─────────────────────────────────────────────────

class TestTrendsAndPredicates:
    def test_the_windowed_churn_is_a_scalar_that_agrees_with_the_rows(self):
        store = _churn_store()
        since = _iso(datetime.now(UTC) - timedelta(days=defs.TREND_DAYS))
        churn = store.membership_churn("crc", since)
        assert churn == {"added": 1, "removed": 1}
        rows = store.membership_events("crc", limit=100)
        inside = [r for r in rows if r["observed_at"] >= since and not r["baseline"]]
        assert len(inside) == churn["added"] + churn["removed"] == 2

    def test_the_predicates_are_spelled_once(self):
        """Neither the store nor the snapshot spells the fragment itself any more: both name it."""
        store_text = Path("gsd/store.py").read_text()
        snapshot_text = Path("gsd/reporting/snapshot.py").read_text()
        assert GROUP_EMPTY == "member_count = 0" and GROUP_UNATTRIBUTED == "sync_provider IS NULL"
        for text, name in ((store_text, "store"), (snapshot_text, "snapshot")):
            assert "GROUP_EMPTY" in text and "GROUP_UNATTRIBUTED" in text, name
            assert "member_count=0" not in text and "member_count = 0" not in text, name
            assert "sync_provider IS NULL" not in text, name

    def test_the_kpi_band_and_the_signed_snapshot_count_the_same_groups(self, tmp_path):
        store = seed_store(str(tmp_path / "w.db"))
        try:
            counts = store.group_counts(CLUSTER)
            listed_empty = store.groups(CLUSTER, state="empty")
            listed_unattributed = store.groups(CLUSTER, state="unattributed")
            path = write_snapshot(store, tmp_path)
        finally:
            store.close()
        with Snapshot(path) as snap:
            report = snap.counts(CLUSTER)
        assert (report["groups"], report["empty_groups"], report["unattributed_groups"]) == \
               (counts["total"], counts["empty"], counts["unattributed"])
        assert (len(listed_empty), len(listed_unattributed)) == (counts["empty"], counts["unattributed"])

    def test_people_counts_agree_with_the_lists_they_head(self, tmp_path):
        store = seed_store(str(tmp_path / "w.db"))
        try:
            people = store.people_counts(CLUSTER)
            assert people["users"] == store.count_users(CLUSTER) == len(store.users(CLUSTER))
            assert people["members"] == len({m["user_name"] for g in store.groups(CLUSTER)
                                             for m in store.group_members(CLUSTER, g["name"])})
        finally:
            store.close()

    def test_the_json_renderer_marks_unavailable_apart_from_zero(self):
        payload = render_json(defs.ALL_KPIS, Context(component="dashboard"))
        assert payload["gsd_process_memory_bytes"]["samples"] is None
        assert payload["users_total"]["privacy"] == INTERNAL and payload["users_total"]["samples"] is None
        store = _churn_store()
        payload = render_json(defs.INTERNAL_KPIS, Context(component="dashboard", store=store, cluster_ids=("crc",)))
        assert payload["membership_added_30d"]["samples"] == [{"cluster": "crc", "value": 1}]
        assert payload["members_total"]["samples"] == [{"cluster": "crc", "value": 2}]


# ── the daily rollup ─────────────────────────────────────────────────────────────────────

class TestRollup:
    def test_written_once_a_day_from_the_live_scalars(self, tmp_path):
        store = seed_store(str(tmp_path / "w.db"))
        try:
            now = datetime(2026, 9, 19, 8, 0, tzinfo=UTC)
            assert rollup.write_if_due(store, CLUSTER, now) is True
            assert rollup.write_if_due(store, CLUSTER, now) is False, "the day's first reading stands"
            series = store.kpi_daily_series(CLUSTER, "groups", "2026-09-01")
            assert series == [{"day": "2026-09-19", "value": float(store.group_counts(CLUSTER)["total"])}]
            assert store.kpi_daily_since(CLUSTER) == "2026-09-19"
            assert rollup.write_if_due(store, CLUSTER, now + timedelta(days=1)) is True
            assert {r["day"] for r in store.kpi_daily_series(CLUSTER, "members", "2026-09-01")} == {"2026-09-19", "2026-09-20"}
            assert tuple(rollup.values(store, CLUSTER)) == defs.ROLLUP_METRICS
        finally:
            store.close()

    def test_pruned_past_its_retention_and_counted_by_table(self, tmp_path):
        store = seed_store(str(tmp_path / "w.db"))
        try:
            old = datetime(2024, 1, 1, tzinfo=UTC)
            rollup.write_if_due(store, CLUSTER, old)
            rollup.write_if_due(store, CLUSTER, datetime(2026, 9, 19, tzinfo=UTC))
            assert rollup.prune(store, CLUSTER, datetime(2026, 9, 19, tzinfo=UTC)) == len(defs.ROLLUP_METRICS)
            assert store.kpi_daily_since(CLUSTER) == "2026-09-19"
        finally:
            store.close()
        assert "kpi_daily" in RETENTION_TABLES

    def test_the_poller_writes_it_as_leader_only(self, tmp_path):
        from gsd.config import ClusterConfig
        from gsd.poller import Poller

        store = seed_store(str(tmp_path / "w.db"))
        try:
            class Elector:
                is_leader = False
            settings = _settings(str(tmp_path / "w.db"))
            poller = Poller(store, settings, elector=Elector())
            cluster = ClusterConfig(CLUSTER, "https://x", token_env="T")
            poller._rollup_kpi(cluster)
            assert store.kpi_daily_since(CLUSTER) is None, "a follower never writes"
            Elector.is_leader = True
            poller._rollup_kpi(cluster)
            assert store.kpi_daily_since(CLUSTER) == rollup.today()
        finally:
            store.close()


# ── the in-app surface ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def kpi_client(tmp_path_factory):
    db = str(tmp_path_factory.mktemp("kpi") / "gsd.db")
    _seed(db)
    app = build_app(_settings(db), run_poller=False)
    app.state.tier_resolver = _MapResolver({"root": "all"})
    with TestClient(app) as c:
        yield c


class TestApi:
    def test_administrator_tier_only(self, kpi_client):
        assert kpi_client.get("/api/kpi", headers=H("alice")).status_code == 403
        body = kpi_client.get("/api/kpi", headers=H("root")).json()
        assert body["scope"] == "all" and body["viewer"] == "root"

    def test_the_payload_states_its_as_of_and_the_retention_edge(self, kpi_client):
        body = kpi_client.get("/api/kpi", headers=H("root")).json()
        assert body["as_of"].endswith("Z")
        assert set(body["kpis"]) == {k.name for k in defs.ALL_KPIS}
        trend = body["trends"]["c1"]
        assert trend["window_days"] == defs.TREND_DAYS
        assert set(trend["history_retained_since"]) == {"membership_event", "sync_event", "binding_event"}
        assert set(trend["daily"]["series"]) == set(defs.ROLLUP_METRICS)
        assert body["kpis"]["users_total"]["privacy"] == INTERNAL
        # The report service has not reported: unavailable, not a block of zeros.
        assert body["system"]["report"] is None

    def test_the_report_system_block_is_what_the_feed_carried(self, kpi_client):
        signals = kpi_client.app.state.signals
        signals.note_report_system({"memory": {"used_bytes": 1, "limit_bytes": 2}}, "2026-09-19T00:00:00Z")
        body = kpi_client.get("/api/kpi", headers=H("root")).json()
        assert body["system"]["report"] == {"as_of": "2026-09-19T00:00:00Z", "memory": {"used_bytes": 1, "limit_bytes": 2}}
        signals.note_report_system(None, "2026-09-19T00:01:00Z")
        assert kpi_client.get("/api/kpi", headers=H("root")).json()["system"]["report"] is None


class TestReportService:
    def test_the_usage_feed_carries_the_service_self_report_and_metrics_carry_component_report(self, tmp_path, monkeypatch):
        from gsd.reporting.server import build_report_app
        from reporting_seed import seeded_dirs
        from test_reporting_server import FROZEN, SECRET, SERVICE, _settings as report_settings

        snapshots, artifacts = seeded_dirs(tmp_path)
        sampler = _sampler(tmp_path)
        monkeypatch.setattr("gsd.kpi.system.CGROUP_ROOT", str(tmp_path / "cgroup"))
        app = build_report_app(report_settings(snapshots, artifacts), secret=SECRET, clock=lambda: FROZEN)
        with TestClient(app) as client:
            usage = client.get("/report/api/usage", headers=SERVICE).json()
            assert usage["system"]["memory"] == {"used_bytes": 105410560, "limit_bytes": 536870912}
            assert usage["system"]["disk"]["total_bytes"] > 0
            text = client.get("/report/metrics").text
        s = _series(text, "gsd_process_memory_bytes")
        assert s == {'gsd_process_memory_bytes{component="report"}': 105410560.0}
        assert "# HELP gsd_membership_changes_total " in text and _series(text, "gsd_membership_changes_total") == {}
