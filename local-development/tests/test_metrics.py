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
          "provider_keys": ["ldap-groupsync_ldap"]}],
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


class TestSqliteMetrics:
    """The WAL series exist and carry real values.

    These three are the only warning of a failure mode with no other symptom: a starved
    checkpoint fills the volume while the pod stays Ready and every other metric looks fine.
    """

    def test_wal_series_are_exposed_with_real_values(self, tmp_path):
        from datetime import timedelta

        from prometheus_client import CollectorRegistry, generate_latest

        from gsd.metrics import DashboardCollector
        from gsd.store import Store

        store = Store(str(tmp_path / "gsd.db"))
        try:
            store.record_poll("c1", "ok", None)
            registry = CollectorRegistry()
            registry.register(DashboardCollector(store, timedelta(seconds=120), None))
            text = generate_latest(registry).decode()

            assert "gsd_sqlite_wal_enabled 1.0" in text, "file-backed store should be in WAL"
            assert "gsd_sqlite_checkpoint_busy_total 0.0" in text
            wal = next(
                float(line.split()[1])
                for line in text.splitlines()
                if line.startswith("gsd_sqlite_wal_bytes ")
            )
            assert wal > 0, "a committed write should leave frames in the WAL"
        finally:
            store.close()

    def test_every_metric_an_alert_references_is_declared_by_the_collector(self):
        """Guards the rename case: an alert on a metric nobody emits never fires, and a
        silent alert is indistinguishable from a healthy system."""
        import re
        import subprocess
        from datetime import timedelta
        from pathlib import Path

        import yaml
        from prometheus_client import CollectorRegistry, generate_latest

        from gsd.metrics import DashboardCollector
        from gsd.store import Store

        chart = Path(__file__).resolve().parents[2] / "charts" / "group-sync-dashboard"
        try:
            rendered = subprocess.run(
                ["helm", "template", "t", str(chart), "-n", "x",
                 "--set", "ingress.host=h",
                 "--set", "monitoring.prometheusRule.enabled=true"],
                capture_output=True, text=True, timeout=120,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pytest.skip("helm not available")
        if rendered.returncode != 0:
            pytest.skip(f"helm template failed: {rendered.stderr[:200]}")

        referenced = set()
        for doc in yaml.safe_load_all(rendered.stdout):
            if doc and doc.get("kind") == "PrometheusRule":
                for group in doc["spec"]["groups"]:
                    for rule in group["rules"]:
                        referenced |= set(re.findall(r"\bgsd_[a-z0-9_]+", rule["expr"]))
        assert referenced, "no gsd_ metrics found in the rules; the probe itself is broken"

        store = Store(":memory:")
        try:
            registry = CollectorRegistry()
            registry.register(DashboardCollector(store, timedelta(seconds=120), None))
            text = generate_latest(registry).decode()
        finally:
            store.close()
        # Declared, not emitted: a per-cluster family yields no series until a cluster is
        # configured, so presence of the HELP line is the right assertion.
        declared = {line.split()[2] for line in text.splitlines() if line.startswith("# HELP")}
        assert not (referenced - declared), f"alerts reference undeclared metrics: {referenced - declared}"

    def test_every_alert_kind_a_rule_references_is_one_the_collector_can_emit(self):
        """The dangling_binding lesson, closed (docs/DESIGN_metrics_refresh.md §5.2).

        The declaration test above holds rules to declared FAMILIES — and still missed the
        gap where gsd_alerts_total was declared while kind="dangling_binding" was a label
        VALUE it never emitted, so a rule on it could never fire. This holds every kind
        matcher in the rules to ALERT_KINDS, the collector's own emittable vocabulary, and
        holds that vocabulary to its two upstream sources so it cannot rot.
        """
        import re
        import subprocess
        from pathlib import Path

        import gsd.metrics as metrics
        import gsd.state

        kinds = getattr(metrics, "ALERT_KINDS", None)
        assert kinds, "gsd.metrics.ALERT_KINDS must enumerate the emittable kind vocabulary"

        # Source one: everything compute_alerts can produce. Read from state.py's own
        # source, because the kinds are string literals at their construction sites and a
        # hand-maintained mirror here would drift exactly like the metric did.
        state_kinds = set(re.findall(r'kind="([a-z_]+)"', Path(gsd.state.__file__).read_text()))
        assert state_kinds, "no kind literals found in state.py; the probe itself is broken"
        assert state_kinds <= set(kinds), f"compute_alerts kinds missing: {state_kinds - set(kinds)}"

        # Source two: the poll outcomes a failing cluster reports as its alert kind.
        from gsd.kube import AUTH_FAILED, FORBIDDEN, UNREACHABLE
        assert {AUTH_FAILED, FORBIDDEN, UNREACHABLE} <= set(kinds)

        chart = Path(__file__).resolve().parents[2] / "charts" / "group-sync-dashboard"
        try:
            rendered = subprocess.run(
                ["helm", "template", "t", str(chart), "-n", "x",
                 "--set", "ingress.host=h",
                 "--set", "monitoring.prometheusRule.enabled=true"],
                capture_output=True, text=True, timeout=120,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pytest.skip("helm not available")
        if rendered.returncode != 0:
            pytest.skip(f"helm template failed: {rendered.stderr[:200]}")
        referenced = set(re.findall(r'gsd_alerts_total\{kind="([a-z_]+)"\}', rendered.stdout))
        assert referenced, "no kind matcher found in the rules; the probe itself is broken"
        assert referenced <= set(kinds), f"rules reference unemittable kinds: {referenced - set(kinds)}"


# ── docs/DESIGN_metrics_refresh.md, applied test-first ─────────────────────────────────────
# Every class below was run against the collector AS IT WAS and failed, before the change it
# tests existed — the fail-before/pass-after discipline the parity gap above showed we need.


class TestAlertsFeedParity:
    """§5.2: gsd_alerts_total's own comment promises parity with /api/alerts. Three ways it
    was broken, three assertions that now hold it."""

    def test_a_degraded_cluster_reports_its_poll_outcome_and_nothing_stale(self, scrape):
        """/api/alerts reports ONE critical alert carrying the poll outcome as its kind and
        suppresses every computed kind — those would be recomputed from cache that stopped
        updating when the poll did. Measured before the fix: the metric did the opposite on
        both counts."""
        text, store = scrape
        assert 'kind="unattributed"' in text, "healthy fixture should alert unattributed"
        store.record_poll("crc", "auth_failed", "401")
        degraded = generate_latest(build_registry(store, GRACE)).decode()
        found = series(degraded, "gsd_alerts_total")
        assert found[
            'gsd_alerts_total{cluster="crc",kind="auth_failed",severity="critical"}'] == 1
        assert 'kind="unattributed"' not in degraded, "stale cache must not alert"

    def test_dangling_bindings_reach_the_alert_metric(self):
        """One dangling row -> kind=dangling_binding, the same count the bindings gauge
        carries. Managed-then-gone is what makes a binding dangling (store._FINDING_CASE)."""
        now = datetime.now(UTC)
        store = Store(":memory:")
        try:
            store.upsert_cluster("crc", "https://x", True)
            store.record_poll("crc", "ok", None)
            store.record_managed_groups(
                "crc", [{"name": "gone-group", "sync_provider": "p"}], _iso(now))
            store.replace_group_state("crc", [], _iso(now))     # the group is gone
            store.replace_bindings(
                "crc",
                [{"binding_kind": "RoleBinding", "binding_namespace": "ns",
                  "binding_name": "rb", "role_kind": "ClusterRole", "role_name": "edit",
                  "group_name": "gone-group"}],
                _iso(now),
            )
            text = generate_latest(build_registry(store, GRACE)).decode()
        finally:
            store.close()
        found = series(text, "gsd_alerts_total")
        assert found[
            'gsd_alerts_total{cluster="crc",kind="dangling_binding",severity="critical"}'] == 1


class TestLeaderLabel:
    def test_gsd_leader_carries_no_vestigial_cluster_label(self, scrape):
        """§5.1: leadership is per-process — one Lease, one flag — and the label was always
        the empty string, asserting a per-cluster fact that does not exist. In PromQL an
        empty label value is indistinguishable from an absent label, so dropping it changes
        no selector."""
        text, _ = scrape
        found = series(text, "gsd_leader")
        assert list(found) == ["gsd_leader"], f"vestigial labels: {list(found)}"


class TestClusterUpHelp:
    def test_the_help_names_the_never_polled_case(self, scrape):
        """§5.3: a never-polled cluster also reads 0, and the HELP must say so — a fresh
        install's 0 read as an outage is the misdiagnosis this line prevents."""
        text, _ = scrape
        help_line = next(
            line for line in text.splitlines() if line.startswith("# HELP gsd_cluster_up "))
        assert "never" in help_line


class TestVisibilitySignals:
    """§3.1/§3.2/§3.3: the process-event counters behind the fail-closed visibility control."""

    def test_tier_check_outcomes_are_counted_and_pre_seeded(self):
        """A counter that first appears at 1 gives increase() no baseline; the whole point
        is catching the FIRST failure, so every enum combination exists at 0."""
        from gsd.metrics import RuntimeSignals
        signals = RuntimeSignals()
        signals.note_tier_check("admin", "forbidden")
        store = Store(":memory:")
        try:
            text = generate_latest(build_registry(store, GRACE, signals=signals)).decode()
        finally:
            store.close()
        found = series(text, "gsd_visibility_tier_checks_total")
        assert found[
            'gsd_visibility_tier_checks_total{outcome="forbidden",threshold="admin"}'] == 1
        assert found[
            'gsd_visibility_tier_checks_total{outcome="unreachable",threshold="usage"}'] == 0
        assert len(found) == 12, "2 thresholds x 6 outcomes, nothing else"

    def test_decisions_count_what_was_served(self):
        from gsd.metrics import RuntimeSignals
        signals = RuntimeSignals()
        signals.note_decision("admin", "self")
        signals.note_decision("admin", "self")
        signals.note_decision("usage", "all")
        store = Store(":memory:")
        try:
            text = generate_latest(build_registry(store, GRACE, signals=signals)).decode()
        finally:
            store.close()
        found = series(text, "gsd_visibility_decisions_total")
        assert found['gsd_visibility_decisions_total{threshold="admin",tier="self"}'] == 2
        assert found['gsd_visibility_decisions_total{threshold="usage",tier="all"}'] == 1
        assert found['gsd_visibility_decisions_total{threshold="usage",tier="self"}'] == 0

    def test_admin_refusals_are_a_plain_counter(self):
        from gsd.metrics import RuntimeSignals
        signals = RuntimeSignals()
        signals.note_admin_refusal()
        signals.note_admin_refusal()
        store = Store(":memory:")
        try:
            text = generate_latest(build_registry(store, GRACE, signals=signals)).decode()
        finally:
            store.close()
        assert series(text, "gsd_visibility_admin_refusals_total") == {
            "gsd_visibility_admin_refusals_total": 2}

    def test_event_families_are_declared_even_unwired(self):
        """The alert-rule tests above resolve rule references against HELP lines, so every
        family must exist on a bare collector — declared empty, claiming no measurements."""
        store = Store(":memory:")
        try:
            text = generate_latest(build_registry(store, GRACE)).decode()
        finally:
            store.close()
        for family in (
            "gsd_visibility_tier_checks_total", "gsd_visibility_decisions_total",
            "gsd_visibility_admin_refusals_total", "gsd_retention_rows_deleted_total",
            "gsd_backup_failures_total", "gsd_cluster_poll_duration_seconds",
            "gsd_login_capture_enabled", "gsd_backup_last_success_timestamp_seconds",
            "gsd_login_capture_last_read_timestamp_seconds",
        ):
            assert f"# HELP {family} " in text, f"{family} not declared"
            assert series(text, family) == {}, f"{family} claims samples while unwired"


class TestRuntimeCounters:
    """§3.6/§3.7/§3.8: the machinery counters, emission and increment sites."""

    def test_retention_deletions_are_counted_by_table(self):
        from gsd.metrics import RuntimeSignals
        signals = RuntimeSignals()
        signals.note_retention("login_event", 5000)
        signals.note_retention("login_event", 137)
        store = Store(":memory:")
        try:
            text = generate_latest(build_registry(store, GRACE, signals=signals)).decode()
        finally:
            store.close()
        found = series(text, "gsd_retention_rows_deleted_total")
        assert found['gsd_retention_rows_deleted_total{table="login_event"}'] == 5137
        assert found['gsd_retention_rows_deleted_total{table="dashboard_user_activity"}'] == 0

    def test_poll_duration_is_exported_per_cluster(self):
        from gsd.metrics import RuntimeSignals
        signals = RuntimeSignals()
        signals.note_poll_duration("crc", 1.42)
        store = Store(":memory:")
        try:
            text = generate_latest(build_registry(store, GRACE, signals=signals)).decode()
        finally:
            store.close()
        assert series(text, "gsd_cluster_poll_duration_seconds")[
            'gsd_cluster_poll_duration_seconds{cluster="crc"}'] == pytest.approx(1.42)

    def test_the_poller_notes_a_failed_backup(self, tmp_path):
        """§3.6's increment site: store.backup returning None IS the failure contract."""
        from gsd.config import Settings
        from gsd.metrics import RuntimeSignals
        from gsd.poller import Poller

        class FailingStore:
            def backup(self, directory, keep=3):
                return None

        signals = RuntimeSignals()
        settings = Settings(clusters=[], db_path=":memory:", backup_dir=str(tmp_path))
        Poller(FailingStore(), settings, None, signals=signals)._maybe_backup()
        assert signals.snapshot()["backup_failures"] == 1

    def test_a_poll_thread_reports_its_duration(self, monkeypatch):
        """§3.7's increment site, end to end: a real poll thread against an unreachable
        endpoint still times its poll — the poll that takes the whole timeout to fail is
        precisely the one worth seeing."""
        import time as _time

        from gsd.config import ClusterConfig, Settings
        from gsd.metrics import RuntimeSignals
        from gsd.poller import Poller

        monkeypatch.setenv("GSD_TEST_POLL_TOKEN", "token")
        signals = RuntimeSignals()
        settings = Settings(
            clusters=[ClusterConfig("nowhere", "https://127.0.0.1:1",
                                    token_env="GSD_TEST_POLL_TOKEN")],
            db_path=":memory:", poll_interval_seconds=3600,
            request_timeout_seconds=0.2, binding_interval_seconds=3600)
        store = Store(":memory:")
        poller = Poller(store, settings, None, signals=signals)
        poller.start()
        try:
            deadline = _time.monotonic() + 10
            while _time.monotonic() < deadline:
                if "nowhere" in signals.snapshot()["poll_seconds"]:
                    break
                _time.sleep(0.05)
        finally:
            poller.stop()
            store.close()
        assert "nowhere" in signals.snapshot()["poll_seconds"]


class TestCaptureAndBackupGauges:
    """§3.4/§3.5/§3.9: machinery-liveness gauges. Absent means never — never zeroed."""

    def test_capture_last_read_is_absent_until_recorded_then_a_timestamp(self):
        store = Store(":memory:")
        try:
            store.upsert_cluster("crc", "https://x", True)
            store.record_poll("crc", "ok", None)
            text = generate_latest(build_registry(store, GRACE)).decode()
            assert "gsd_login_capture_last_read_timestamp_seconds{" not in text
            store.record_login_read("crc", "2026-08-10T12:00:00Z")
            text = generate_latest(build_registry(store, GRACE)).decode()
            assert series(text, "gsd_login_capture_last_read_timestamp_seconds")[
                'gsd_login_capture_last_read_timestamp_seconds{cluster="crc"}'
            ] > 1_700_000_000
        finally:
            store.close()

    def test_backup_timestamp_reads_the_newest_file(self, tmp_path):
        """From the files, not from memory of the last attempt: it survives restarts and
        measures the artifact a restore would actually use."""
        from types import SimpleNamespace
        (tmp_path / "gsd-20260810T000000.000000Z.db").write_bytes(b"x")
        settings = SimpleNamespace(backup_dir=str(tmp_path), login_capture_enabled=False)
        store = Store(":memory:")
        try:
            text = generate_latest(
                build_registry(store, GRACE, settings=settings)).decode()
        finally:
            store.close()
        value = series(text, "gsd_backup_last_success_timestamp_seconds")[
            "gsd_backup_last_success_timestamp_seconds"]
        expected = (tmp_path / "gsd-20260810T000000.000000Z.db").stat().st_mtime
        assert value == pytest.approx(expected, abs=1)

    def test_backup_timestamp_is_absent_when_backups_are_off_or_none_exist(self, tmp_path):
        from types import SimpleNamespace
        store = Store(":memory:")
        try:
            for backup_dir in ("", str(tmp_path)):
                settings = SimpleNamespace(backup_dir=backup_dir, login_capture_enabled=False)
                text = generate_latest(
                    build_registry(store, GRACE, settings=settings)).decode()
                assert series(text, "gsd_backup_last_success_timestamp_seconds") == {}
        finally:
            store.close()

    def test_capture_enabled_reflects_the_setting(self):
        from types import SimpleNamespace
        store = Store(":memory:")
        try:
            for enabled in (True, False):
                settings = SimpleNamespace(backup_dir="", login_capture_enabled=enabled)
                text = generate_latest(
                    build_registry(store, GRACE, settings=settings)).decode()
                assert series(text, "gsd_login_capture_enabled") == {
                    "gsd_login_capture_enabled": 1 if enabled else 0}
        finally:
            store.close()


class TestGroupCountCliffMetric:
    def _store(self, silence=None):
        now = datetime.now(UTC)
        store = Store(":memory:")
        store.upsert_cluster("crc", "https://x", True)
        store.record_poll("crc", "ok", None)
        store.sync_members("crc", {"big": [f"u{i}" for i in range(20)]}, {}, "2026-01-01T00:00:00Z")
        store.sync_members("crc", {"big": ["u0"]}, {}, _iso(now))
        store.replace_group_state("crc", [{"name": "big", "member_count": 1, "sync_provider": "gs",
                                           "group_synced_at": None, "ldap_uid": None,
                                           "cliff_silence": silence}], _iso(now))
        return store

    def test_kind_only_never_the_group_name(self):
        from gsd.config import Settings
        store = self._store()
        try:
            text = generate_latest(build_registry(store, GRACE, settings=Settings())).decode()
        finally:
            store.close()
        assert series(text, "gsd_alerts_total")[
            'gsd_alerts_total{cluster="crc",kind="group_count_cliff",severity="warning"}'] == 1
        assert "big" not in text.replace("gsd_build_info", ""), "a group name reached /metrics"

    def test_silenced_counts_under_its_own_kind(self):
        from gsd.config import Settings
        store = self._store(silence="true")
        try:
            text = generate_latest(build_registry(store, GRACE, settings=Settings())).decode()
        finally:
            store.close()
        got = series(text, "gsd_alerts_total")
        assert got['gsd_alerts_total{cluster="crc",kind="group_count_cliff_silenced",severity="warning"}'] == 1
        assert 'kind="group_count_cliff",' not in text

    def test_no_settings_means_module_off_on_the_collector(self):
        """A bare DashboardCollector(store, grace) claims no cliff: the policy derives from
        settings, and None is the off state — the same rule as the event families."""
        store = self._store()
        try:
            text = generate_latest(build_registry(store, GRACE)).decode()
        finally:
            store.close()
        # The HELP line names the kind; what must be absent is a SERIES carrying it.
        assert 'kind="group_count_cliff' not in text

    def test_the_rule_renders_with_defaults_and_is_derived_away_when_the_module_is_off(self):
        import subprocess
        from pathlib import Path
        chart = Path(__file__).resolve().parents[2] / "charts" / "group-sync-dashboard"

        def rules(*sets):
            args = ["helm", "template", "t", str(chart), "-n", "x", "--set", "ingress.host=h",
                    "--set", "monitoring.prometheusRule.enabled=true", *sum((["--set", s] for s in sets), [])]
            try:
                done = subprocess.run(args, capture_output=True, text=True, timeout=120)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pytest.skip("helm not available")
            assert done.returncode == 0, done.stderr
            # The PrometheusRule alone: the Grafana dashboard (on by default since chart 0.14.0)
            # names every rule in a text panel, which would satisfy a whole-render substring test.
            chunks = [c for c in done.stdout.split("\n---\n") if "kind: PrometheusRule" in c]
            assert len(chunks) == 1, "expected exactly one PrometheusRule document"
            return chunks[0]

        on = rules()
        assert "alert: GroupSyncGroupCountCliff" in on
        assert 'gsd_alerts_total{kind="group_count_cliff"} > 0' in on
        assert 'kind="group_count_cliff_silenced"' not in on, "a silenced cliff must never page"
        off = rules("config.alerts.groupCountCliff.enabled=false")
        assert "GroupSyncGroupCountCliff" not in off
