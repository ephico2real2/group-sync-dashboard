"""The read-only backend (docs/specs/SPEC_C3_reporting_microservice.md §9.3): which copy is read, that it
cannot be written, that its classification is the Store's, and that a newer schema is refused."""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from gsd.store import Store, _MIGRATIONS
from gsd.reporting.snapshot import KNOWN_SCHEMA_VERSION, Snapshot, SnapshotError, newest_snapshot
from reporting_seed import CLUSTER, NOW, seed_store, write_snapshot


@pytest.fixture()
def seeded(tmp_path):
    store = seed_store(str(tmp_path / "writer.db"))
    d = tmp_path / "snapshots"
    d.mkdir()
    path = write_snapshot(store, d)
    yield store, d, path
    store.close()


class TestWhichCopy:
    def test_newest_by_name_and_tmp_files_are_never_candidates(self, tmp_path):
        d = tmp_path / "s"; d.mkdir()
        for name in ("gsd-20260906T100000.000000Z.db", "gsd-20260906T120000.000000Z.db", "gsd-20260906T130000.000000Z.db.tmp", "notes.txt"):
            (d / name).write_bytes(b"")
        assert newest_snapshot(str(d)).name == "gsd-20260906T120000.000000Z.db"

    def test_a_missing_or_empty_directory_names_the_interval_setting(self, tmp_path):
        with pytest.raises(SnapshotError, match="does not exist"):
            newest_snapshot(str(tmp_path / "nope"))
        (tmp_path / "empty").mkdir()
        with pytest.raises(SnapshotError, match="reporting.snapshot.intervalSeconds"):
            newest_snapshot(str(tmp_path / "empty"))

    def test_the_stamp_is_the_filename_in_iso_form(self, seeded):
        _, _, path = seeded
        with Snapshot(path) as snap:
            assert snap.info().stamp.endswith("Z") and snap.info().stamp[10] == "T"
            assert snap.info().bytes > 0 and snap.info().age_seconds(datetime.now(UTC)) >= 0


class TestReadOnlyByConstruction:
    def test_a_link_named_like_a_copy_is_refused_at_listing_and_at_open(self, tmp_path):
        """Codex, review C3: the report pod mounts the whole data claim read-only, so a symlink named
        like a copy could point at the live gsd.db — and immutable=1 on a changing file returns wrong
        results. Regular files only, judged without following links."""
        live = tmp_path / "gsd.db"
        w = sqlite3.connect(live); w.execute("PRAGMA journal_mode=WAL"); w.execute("CREATE TABLE proof(v TEXT)"); w.commit(); w.close()
        d = tmp_path / "report"; d.mkdir()
        link = d / "gsd-20260906T120000.000000Z.db"; link.symlink_to(live)
        with pytest.raises(SnapshotError, match="reporting.snapshot.intervalSeconds"):
            newest_snapshot(str(d))                        # the link is not a candidate
        with pytest.raises(SnapshotError, match="not a regular snapshot file"):
            Snapshot(link)                                 # and not openable by name either
        (d / "gsd-20260906T120001.000000Z.db").mkdir()
        with pytest.raises(SnapshotError):
            Snapshot(d / "gsd-20260906T120001.000000Z.db")


    def test_the_copy_is_rollback_journal_and_refuses_a_write(self, seeded):
        _, _, path = seeded
        with Snapshot(path) as snap:
            assert snap._conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                snap._conn.execute("DELETE FROM group_state")

    def test_a_newer_schema_is_refused_naming_both_numbers(self, seeded):
        _, d, path = seeded
        newer = d / "gsd-20990101T000000.000000Z.db"
        newer.write_bytes(path.read_bytes())
        c = sqlite3.connect(newer); c.execute(f"PRAGMA user_version = {KNOWN_SCHEMA_VERSION + 1}"); c.commit(); c.close()
        with pytest.raises(SnapshotError) as exc:
            Snapshot(newer)
        assert str(KNOWN_SCHEMA_VERSION + 1) in str(exc.value) and str(KNOWN_SCHEMA_VERSION) in str(exc.value)
        assert KNOWN_SCHEMA_VERSION == max(t for t, _, _ in _MIGRATIONS)

    def test_an_open_snapshot_survives_the_writer_pruning_its_path(self, tmp_path):
        path = tmp_path / "gsd-20260905T120000.000000Z.db"
        w = sqlite3.connect(path)
        w.execute("CREATE TABLE proof(value TEXT NOT NULL)"); w.execute("INSERT INTO proof(value) VALUES('still readable')")
        w.execute(f"PRAGMA user_version = {KNOWN_SCHEMA_VERSION}"); w.commit(); w.close()
        expected_bytes = path.stat().st_size
        with Snapshot(path) as snapshot:
            path.unlink()
            assert not path.exists()
            assert snapshot.info().bytes == expected_bytes
            assert snapshot._rows("SELECT value FROM proof") == [{"value": "still readable"}]


class TestTheClassificationIsTheStores:
    def test_group_bindings_agree_with_all_bindings_row_for_row(self, seeded):
        store, _, path = seeded
        expected_all = sorted((b["finding"], b["group_name"], b["binding_namespace"], b["binding_name"])
                              for b in store.all_bindings(CLUSTER))
        expected = [row for row in expected_all if not row[1].startswith("system:")]
        with Snapshot(path) as snap:
            got = sorted((b["finding"], b["group_name"], b["binding_namespace"], b["binding_name"])
                         for b in snap.group_bindings(CLUSTER))
            assert got == expected
            assert {"dangling", "unresolved", "unmanaged", "ok"} <= {g[0] for g in got}
            assert "built_in" not in {g[0] for g in got}
            assert any(row[1].startswith("system:") for row in expected_all), (
                "the Store still has the virtual group; only the report listing drops it")
            counts = snap.findings_counts(CLUSTER)
        assert counts == {k: sum(1 for g in got if g[0] == k) for k in counts}
        assert "built_in" not in counts
        assert store.count_bindings_by_finding(CLUSTER).get("built_in", 0) >= 1

    def test_namespaces_are_pending_before_any_read_and_the_tables_exist(self, seeded):
        _, _, path = seeded
        with Snapshot(path) as snap:
            assert snap.has_table("cluster_namespace") and snap.has_table("report_run")
            assert snap.namespaces_source(CLUSTER) is None and snap.cluster_namespaces(CLUSTER) == []

    def test_the_login_gate_views_match_the_store_and_are_empty_without_a_gate(self, tmp_path):
        store = seed_store(str(tmp_path / "w.db"))
        d = tmp_path / "s"; d.mkdir(); path = write_snapshot(store, d)
        with Snapshot(path) as snap:
            assert sorted(r["user_name"] for r in snap.access_without_login(CLUSTER)) == sorted(r["user_name"] for r in store.access_without_login(CLUSTER))
            assert [r["user_name"] for r in snap.login_without_access(CLUSTER)] == ["dave"]
            rejected = snap.rejected_attempts(CLUSTER, "2000-01-01T00:00:00Z")
            assert {r["user_name"]: bool(r["in_access_group"]) for r in rejected} == {"mallory": False, "carol": False}
        store.close()
        store = seed_store(str(tmp_path / "w2.db"), gate=False)
        d2 = tmp_path / "s2"; d2.mkdir(); path2 = write_snapshot(store, d2)
        with Snapshot(path2) as snap:
            assert snap.access_without_login(CLUSTER) == [] and snap.login_without_access(CLUSTER) == []
            assert all(r["in_access_group"] is None for r in snap.rejected_attempts(CLUSTER, "2000-01-01T00:00:00Z"))
        store.close()

    def test_the_raw_error_text_is_never_selected(self, seeded):
        from reporting_seed import RAW_ERROR
        _, _, path = seeded
        with Snapshot(path) as snap:
            crs = snap.groupsyncs(CLUSTER)
            assert crs and crs[0]["has_error_message"] == 1
            assert RAW_ERROR not in repr(crs) and "error_message" not in crs[0]
