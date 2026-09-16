"""Extension B2 — the namespace-access report selects namespaces by a captured metadata key
(docs/DESIGN_reporting_auditors_and_ns_selector.md §3.5–3.6). The capture is B1 (already merged)."""
from __future__ import annotations

from pathlib import Path

import pytest

from gsd.store import Store
from gsd.reporting.snapshot import Snapshot
from gsd.reporting.catalogue import REGISTRY
from gsd.reporting.catalogue.common import RunContext, ValidationError, assemble, validate_params
from gsd.reporting.config import ReportSettings

CLUSTER = "crc-local"
LABEL = "company.net/mnemonic"


def _snap(tmp_path: Path) -> Snapshot:
    store = Store(str(tmp_path / "w.db"))
    store.upsert_cluster(CLUSTER, "https://k8s", True)
    store.replace_namespaces(CLUSTER, [
        {"name": "beta-prod", "created_at": None, "phase": "Active", "metadata": {LABEL: "beta"}},
        {"name": "beta-rnd", "created_at": None, "phase": "Active", "metadata": {LABEL: "beta"}},
        {"name": "demo-prod", "created_at": None, "phase": "Active", "metadata": {LABEL: "demo"}},
        {"name": "unlabelled", "created_at": None, "phase": "Active", "metadata": {}},
    ], "2026-09-14T00:00:00Z")
    path = store.snapshot(str(tmp_path), keep=2); store.close()
    return Snapshot(Path(path))


class TestSnapshotSelectorMethods:
    def test_distinct_values_for_the_key(self, tmp_path):
        with _snap(tmp_path) as s:
            assert s.namespace_metadata_values(CLUSTER, LABEL) == ["beta", "demo"]

    def test_values_empty_for_an_uncaptured_key_or_empty_key(self, tmp_path):
        with _snap(tmp_path) as s:
            assert s.namespace_metadata_values(CLUSTER, "company.net/other") == []
            assert s.namespace_metadata_values(CLUSTER, "") == []

    def test_expansion_returns_the_matching_namespaces(self, tmp_path):
        with _snap(tmp_path) as s:
            assert s.namespaces_for_metadata(CLUSTER, LABEL, ["beta"]) == ["beta-prod", "beta-rnd"]
            assert s.namespaces_for_metadata(CLUSTER, LABEL, ["beta", "demo"]) == ["beta-prod", "beta-rnd", "demo-prod"]
            assert s.namespaces_for_metadata(CLUSTER, LABEL, ["nope"]) == []
            assert s.namespaces_for_metadata(CLUSTER, LABEL, []) == []


class TestTheValidator:
    def _spec(self):
        return REGISTRY["namespace-access"][0]

    def test_both_mnemonics_and_namespaces_is_422(self):
        with pytest.raises(ValidationError, match="not more than one"):
            validate_params(self._spec(), {"mnemonics": "beta", "namespaces": "prod-ns"})

    def test_neither_is_422(self):
        with pytest.raises(ValidationError, match="select at least one namespace"):
            validate_params(self._spec(), {})

    def test_more_than_50_mnemonics_is_422(self):
        many = ",".join(f"v{i}" for i in range(51))
        with pytest.raises(ValidationError, match="at most 50 mnemonic values"):
            validate_params(self._spec(), {"mnemonics": many})

    def test_mnemonics_alone_validates(self):
        out = validate_params(self._spec(), {"mnemonics": "beta,demo"})
        assert out["mnemonics"] == ["beta", "demo"] and out["namespaces"] is None

    def test_namespaces_alone_still_validates(self):
        out = validate_params(self._spec(), {"namespaces": "prod-ns"})
        assert out["namespaces"] == ["prod-ns"] and out["mnemonics"] is None


class TestBuildExpandsMnemonics:
    def _ctx(self, snap, label=LABEL):
        info = snap.info()
        return RunContext(settings=ReportSettings(), cluster=snap.cluster(CLUSTER), now=info.stamp and __import__("datetime").datetime(2026,9,14),
                          run_id="r", generated_by="root", generated_by_note="n", snapshot_stamp=info.stamp,
                          snapshot_age_seconds=0.0, schema_version=info.schema_version, namespace_selector_labels=(label,) if label else ())

    def test_mnemonic_expands_to_its_namespaces(self, tmp_path):
        with _snap(tmp_path) as snap:
            spec, build = REGISTRY["namespace-access"]
            p = validate_params(spec, {"mnemonics": "beta"})
            report = assemble(spec, snap, self._ctx(snap), p, build(snap, self._ctx(snap), p))
            titles = [s.title for s in report.sections]
            assert "Namespace: beta-prod" in titles and "Namespace: beta-rnd" in titles
            assert "Namespace: demo-prod" not in titles

    def test_a_mnemonic_matching_nothing_is_a_failed_run(self, tmp_path):
        with _snap(tmp_path) as snap:
            spec, build = REGISTRY["namespace-access"]
            p = validate_params(spec, {"mnemonics": "nope"})
            with pytest.raises(ValidationError, match="no namespace carries"):
                build(snap, self._ctx(snap), p)


class TestSelectorCapAndGuards:
    """F1/F3 from review #112: a selector cap is recorded in Coverage, NOT as a row-cut Truncation
    note; a mnemonic with no selector key configured is a clear 422, not 'no namespace carries…'."""

    def _big_snap(self, tmp_path: Path, count: int) -> Snapshot:
        store = Store(str(tmp_path / "big.db"))
        store.upsert_cluster(CLUSTER, "https://k8s", True)
        store.replace_namespaces(CLUSTER, [
            {"name": f"cap-{i:03d}", "created_at": None, "phase": "Active", "metadata": {LABEL: "big"}}
            for i in range(count)
        ], "2026-09-14T00:00:00Z")
        path = store.snapshot(str(tmp_path), keep=2); store.close()
        return Snapshot(Path(path))

    def _ctx(self, snap, label=LABEL):
        info = snap.info()
        return RunContext(settings=ReportSettings(), cluster=snap.cluster(CLUSTER),
                          now=__import__("datetime").datetime(2026, 9, 14), run_id="r",
                          generated_by="root", generated_by_note="n", snapshot_stamp=info.stamp,
                          snapshot_age_seconds=0.0, schema_version=info.schema_version,
                          namespace_selector_labels=(label,) if label else ())

    def test_over_50_is_a_coverage_note_not_a_truncation_note(self, tmp_path):
        with self._big_snap(tmp_path, 60) as snap:
            spec, build = REGISTRY["namespace-access"]
            p = validate_params(spec, {"mnemonics": "big"})
            built = build(snap, self._ctx(snap), p)
            # A 60→50 selector cap is not a ROW_LIMIT cut: `totals` is honest, so no Truncation note.
            assert built.truncated is False
            report = assemble(spec, snap, self._ctx(snap), p, built)
            titles = [s.title for s in report.sections]
            assert "Coverage" in titles
            assert "Truncation" not in titles
            # 50 namespace sections + the one Coverage section.
            assert sum(1 for t in titles if t.startswith("Namespace: ")) == 50

    def test_mnemonic_with_no_selector_configured_is_a_clear_422(self, tmp_path):
        with _snap(tmp_path) as snap:
            spec, build = REGISTRY["namespace-access"]
            p = validate_params(spec, {"mnemonics": "beta"})
            with pytest.raises(ValidationError, match="not configured"):
                build(snap, self._ctx(snap, label=""), p)


# ── P2: multi-dimension selector (company.net/mnemonic AND company.net/app-environment) ──────────
LABEL2 = "company.net/app-environment"


def _snap_two_dim(tmp_path: Path) -> Snapshot:
    store = Store(str(tmp_path / "w2.db"))
    store.upsert_cluster(CLUSTER, "https://k8s", True)
    store.replace_namespaces(CLUSTER, [
        {"name": "beta-prod",  "created_at": None, "phase": "Active", "metadata": {LABEL: "beta", LABEL2: "prod"}},
        {"name": "beta-rnd",   "created_at": None, "phase": "Active", "metadata": {LABEL: "beta", LABEL2: "rnd"}},
        {"name": "demo-prod",  "created_at": None, "phase": "Active", "metadata": {LABEL: "demo", LABEL2: "prod"}},
        {"name": "demo-qa",    "created_at": None, "phase": "Active", "metadata": {LABEL: "demo", LABEL2: "qa"}},
        {"name": "gsd-shared", "created_at": None, "phase": "Active", "metadata": {LABEL: "gsd"}},  # missing env
    ], "2026-09-14T00:00:00Z")
    path = store.snapshot(str(tmp_path), keep=2); store.close()
    return Snapshot(Path(path))


def _ctx_two_dim(snap):
    import datetime
    info = snap.info()
    return RunContext(settings=ReportSettings(), cluster=snap.cluster(CLUSTER),
                      now=datetime.datetime(2026, 9, 14), run_id="r", generated_by="root",
                      generated_by_note="n", snapshot_stamp=info.stamp, snapshot_age_seconds=0.0,
                      schema_version=info.schema_version,
                      namespace_selector_labels=(LABEL, LABEL2))


class TestMultiDimensionSelector:
    def test_and_across_or_within(self, tmp_path):
        with _snap_two_dim(tmp_path) as s:
            assert s.namespaces_for_selectors(CLUSTER, {LABEL: ["beta", "demo"], LABEL2: ["prod"]}) == ["beta-prod", "demo-prod"]
            assert s.namespaces_for_selectors(CLUSTER, {LABEL: ["demo"], LABEL2: ["prod", "qa"]}) == ["demo-prod", "demo-qa"]
            assert s.namespaces_for_selectors(CLUSTER, {LABEL2: ["prod"]}) == ["beta-prod", "demo-prod"]
            assert s.namespaces_for_selectors(CLUSTER, {LABEL: ["beta"], LABEL2: ["qa"]}) == []
            assert s.namespaces_for_selectors(CLUSTER, {}) == []

    def test_missing_dimension_namespace_drops_from_the_AND(self, tmp_path):
        with _snap_two_dim(tmp_path) as s:
            assert "gsd-shared" not in s.namespaces_for_selectors(CLUSTER, {LABEL: ["gsd"], LABEL2: ["prod"]})
            assert s.namespaces_for_selectors(CLUSTER, {LABEL: ["gsd"]}) == ["gsd-shared"]

    def test_dimensions_gather_for_the_catalogue(self, tmp_path):
        with _snap_two_dim(tmp_path) as s:
            assert s.namespace_selector_dimensions([LABEL, LABEL2])[CLUSTER] == [
                {"label": LABEL, "values": ["beta", "demo", "gsd"]},
                {"label": LABEL2, "values": ["prod", "qa", "rnd"]},
            ]

    def test_build_expands_selectors_and(self, tmp_path):
        with _snap_two_dim(tmp_path) as snap:
            spec, build = REGISTRY["namespace-access"]
            p = validate_params(spec, {"selectors": {LABEL: ["demo"], LABEL2: ["prod", "qa"]}})
            titles = [s.title for s in build(snap, _ctx_two_dim(snap), p).sections]
            assert "Namespace: demo-prod" in titles and "Namespace: demo-qa" in titles
            assert "Namespace: beta-prod" not in titles

    def test_unknown_selector_label_is_a_failed_run(self, tmp_path):
        with _snap_two_dim(tmp_path) as snap:
            spec, build = REGISTRY["namespace-access"]
            p = validate_params(spec, {"selectors": {"company.net/nope": ["x"]}})
            with pytest.raises(ValidationError, match="not configured on this deployment"):
                build(snap, _ctx_two_dim(snap), p)

    def test_selectors_matching_nothing_is_a_failed_run(self, tmp_path):
        with _snap_two_dim(tmp_path) as snap:
            spec, build = REGISTRY["namespace-access"]
            p = validate_params(spec, {"selectors": {LABEL: ["beta"], LABEL2: ["qa"]}})
            with pytest.raises(ValidationError, match="no namespace matches"):
                build(snap, _ctx_two_dim(snap), p)


class TestSelectorMapValidation:
    def _spec(self):
        return REGISTRY["namespace-access"][0]

    def test_valid_selector_map_dedups(self):
        p = validate_params(self._spec(), {"selectors": {LABEL: ["beta", "beta", "demo"]}})
        assert p["selectors"] == {LABEL: ["beta", "demo"]}

    def test_empty_dimension_is_422(self):
        with pytest.raises(ValidationError, match="at least one value"):
            validate_params(self._spec(), {"selectors": {LABEL: []}})

    def test_non_object_is_422(self):
        with pytest.raises(ValidationError, match="non-empty object"):
            validate_params(self._spec(), {"selectors": "beta"})

    def test_selectors_and_namespaces_is_422(self):
        with pytest.raises(ValidationError, match="not more than one"):
            validate_params(self._spec(), {"selectors": {LABEL: ["beta"]}, "namespaces": "x"})

    def test_aggregate_value_cap_is_422(self):
        with pytest.raises(ValidationError, match="at most 50 selector values"):
            validate_params(self._spec(), {"selectors": {LABEL: [f"v{i}" for i in range(51)]}})

    def test_dimension_requires_a_list_not_a_csv_string(self):
        # The grammar is dict[str, list[str]]; a comma string must NOT be split (review #129 C1, Codex).
        with pytest.raises(ValidationError, match="must be a list of strings"):
            validate_params(self._spec(), {"selectors": {LABEL: "beta,demo"}})
