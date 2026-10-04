from datetime import timedelta

from gsd import loginlog
from gsd.reporting.snapshot import Snapshot
from gsd.store import Store
from reporting_seed import CLUSTER, NOW, _iso, write_snapshot
from test_report_seal import _run


def _block(report, title):
    return next(b for s in report.sections for b in s.blocks if getattr(b, "title", None) == title)


def test_windows_stop_inclusively_at_the_snapshot_stamp(tmp_path, monkeypatch):
    """A real Store snapshot may contain a source timestamp ahead of the copy clock. The reports' windows end at
    the stamp: the row at it is included, the row one second after it is not."""
    import gsd.store
    now = _iso(NOW)
    monkeypatch.setattr(gsd.store, "now_iso", lambda: now)
    store = Store(str(tmp_path / "writer.db"))
    store.upsert_cluster(CLUSTER, "https://api.crc.testing:6443", True)
    store.record_poll(CLUSTER, "ok", None)
    boundary = NOW - timedelta(minutes=22)
    store.replace_groupsync_state(CLUSTER, [
        {"name": name, "namespace": "group-sync-operator", "schedule": "*/10 * * * *", "ldap_filter": "x",
         "last_sync_at": _iso(boundary + timedelta(seconds=delta)), "generation": 1, "provider_keys": []}
        for name, delta in (("before", -1), ("at", 0), ("after", 1))
    ], now)
    initial = ["window-before", "window-at", "window-after", "dormant-before", "dormant-at", "dormant-after"]
    store.replace_group_state(CLUSTER, [{"name": "edge", "member_count": 9, "sync_provider": None,
                                         "group_synced_at": now, "ldap_uid": None}], now)
    members = list(initial)
    store.sync_members(CLUSTER, {"edge": members}, {"edge": now}, _iso(NOW - timedelta(days=40)))
    for name, delta in (("member-before", -1), ("member-at", 0), ("member-after", 1)):
        members.append(name)
        store.sync_members(CLUSTER, {"edge": members}, {"edge": now}, _iso(NOW + timedelta(seconds=delta)))
    store.replace_users(CLUSTER, [
        {"user_name": name, "full_name": None, "created_at": now, "providers": ["ldap"], "has_identity": True}
        for name in initial
    ], now)
    store.record_login_read(CLUSTER, now)
    events = []
    for name, at in (("window-before", NOW - timedelta(seconds=1)), ("window-at", NOW),
                     ("window-after", NOW + timedelta(seconds=1)),
                     ("dormant-before", NOW - timedelta(days=1, seconds=1)),
                     ("dormant-at", NOW - timedelta(days=1)),
                     ("dormant-after", NOW - timedelta(days=1) + timedelta(seconds=1))):
        events.append({"pod_name": "oauth-1", "user_name": name, "outcome": loginlog.OUTCOME_SUCCESS,
                       "at": at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"), "provider": "ldap", "ldap_result_code": None, "detail": None,
                       "observed_at": now})
    store.record_login_events(CLUSTER, events)
    for delta in (-1, 0, 1):
        at = _iso(NOW + timedelta(seconds=delta))
        store.record_sync_event(CLUSTER, "at", "group-sync-operator", at, at, "*/10 * * * *", 1)
    store.replace_bindings(CLUSTER, [], now)
    store.replace_user_bindings(CLUSTER, [], now)
    store.replace_operator_configs(CLUSTER, None, now)
    directory = tmp_path / "snapshots"
    directory.mkdir()
    path = write_snapshot(store, directory)
    store.close()

    with Snapshot(path) as snap:
        login = _run(snap, "login-activity", params={"window_days": 1})
        users = {row[0] for row in _block(login, "Users").rows}
        assert {"window-before", "window-at"} <= users and "window-after" not in users

        groups = _run(snap, "groups", params={"window_days": 1})
        changed = {row[3] for row in _block(groups, "Changes").rows}
        assert {"member-before", "member-at"} <= changed and "member-after" not in changed

        health = _run(snap, "groupsync-health", params={"window_days": 1})
        crs = {row[0].rsplit("/", 1)[1]: row for row in _block(health, "CRs").rows}
        assert crs["at"][5] == 2
        assert {name: row[2] for name, row in crs.items()} == {"before": "overdue", "at": "late", "after": "late"}

        compliance = _run(snap, "compliance-snapshot")
        figures = dict(_block(compliance, "Directory and users").items)
        pipeline = dict(_block(compliance, "Sync pipeline").items)
        assert figures["Members added / removed, 30 d"] == "2 / 0"
        assert pipeline["Overdue"] == 1

        dormant = _run(snap, "dormant-access", params={"dormant_days": 1})
        dormant_users = {row[0] for row in _block(dormant, "Members who have logged in before, not recently").rows}
        assert dormant_users == {"dormant-before", "window-after"}
