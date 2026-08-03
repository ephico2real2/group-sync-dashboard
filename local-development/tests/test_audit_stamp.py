"""The unmanaged-audit stamping invariants, one test per design clause.

docs/unmanaged-audit-design.md is the spec; this file is its enforcement. This is the
dashboard's only write path, which is why the decisions live in a pure module
(gsd/audit.py) where every invariant is a plain assertion.
"""

from __future__ import annotations

import pytest

from gsd.audit import plan_audit_stamps
from gsd.config import Settings, load_settings
from gsd.kube import (
    UNMANAGED_DETECTED_AT_ANNOTATION,
    UNMANAGED_DETECTED_BY_ANNOTATION,
    UNMANAGED_LABEL,
)


def _row(name, finding="unmanaged", stamped=False, kind="RoleBinding", ns="ns-a",
         group="app-ocp-rbac-team-ns-admin", role="admin"):
    return {"binding_kind": kind, "binding_namespace": ns, "binding_name": name,
            "group_name": group, "finding": finding, "audit_stamped": stamped,
            "role_name": role}


class TestI2TargetSet:
    def test_only_unmanaged_rows_are_stamped(self):
        plan = plan_audit_stamps([
            _row("hand-made"),
            _row("healthy", finding="ok"),
            _row("broken", finding="dangling"),
            _row("virtual", finding="built_in"),
            _row("never-seen", finding="unresolved"),
        ])
        assert plan.stamp == [("RoleBinding", "ns-a", "hand-made")]

    def test_a_multi_subject_binding_is_one_object_not_two(self):
        """demo-monitoring-config-rb names two groups, so it arrives as two rows — and the
        rows can be classified differently. One patch per object, if ANY row is unmanaged."""
        plan = plan_audit_stamps([
            _row("multi", group="group-a", finding="unmanaged"),
            _row("multi", group="group-b", finding="ok"),
        ])
        assert plan.stamp == [("RoleBinding", "ns-a", "multi")]

    def test_nothing_to_do_is_an_empty_plan(self):
        plan = plan_audit_stamps([_row("healthy", finding="ok")])
        assert plan.stamp == [] and plan.unstamp == [] and plan.capped == 0


class TestI3Idempotency:
    def test_an_already_stamped_binding_is_never_patched_again(self):
        plan = plan_audit_stamps([_row("already", stamped=True)])
        assert plan.stamp == [], "re-stamping would overwrite the first-detected timestamp"


class TestI4SelfHealing:
    def test_a_stamped_binding_no_longer_unmanaged_is_healed(self):
        for now_finding in ("ok", "dangling", "built_in", "unresolved"):
            plan = plan_audit_stamps([_row("adopted", finding=now_finding, stamped=True)])
            assert plan.unstamp == [("RoleBinding", "ns-a", "adopted")], now_finding

    def test_a_multi_subject_binding_heals_only_when_no_row_is_unmanaged(self):
        plan = plan_audit_stamps([
            _row("multi", group="a", finding="unmanaged", stamped=True),
            _row("multi", group="b", finding="ok", stamped=True),
        ])
        assert plan.unstamp == [], "one subject still unmanaged — the label must stay"

    def test_healing_is_never_capped(self):
        """A wrong stamp must never queue behind new detections to be corrected."""
        rows = [_row(f"heal-{i}", finding="ok", stamped=True) for i in range(50)]
        plan = plan_audit_stamps(rows, max_per_cycle=5)
        assert len(plan.unstamp) == 50


class TestI6BlastRadius:
    def test_stamps_are_capped_and_the_deferral_is_counted(self):
        rows = [_row(f"b-{i:03d}") for i in range(30)]
        plan = plan_audit_stamps(rows, max_per_cycle=20)
        assert len(plan.stamp) == 20
        assert plan.capped == 10

    def test_deterministic_order_so_deferred_stamps_converge(self):
        """The cap takes a sorted prefix: the same objects are not re-deferred forever."""
        rows = [_row(f"b-{i:03d}") for i in range(30)]
        first = plan_audit_stamps(rows, max_per_cycle=20).stamp
        again = plan_audit_stamps(rows, max_per_cycle=20).stamp
        assert first == again == sorted(first)


class TestI5ModeGating:
    def test_an_unrecognised_mode_fails_safe_to_off(self, tmp_path, monkeypatch):
        """A word that means something else, or nothing, must not enable discovery."""
        base = (tmp_path / "c.yaml")
        base.write_text("clusters:\n  - name: c\n    apiUrl: https://x\n    tokenEnv: T\n")
        for bad in ("on", "true", "yes", "enable", "anotate", "logg"):
            monkeypatch.setenv("GSD_UNMANAGED_AUDIT_MODE", bad)
            assert load_settings(str(base)).unmanaged_audit_mode == "off", bad

    def test_annotate_downgrades_to_log_rather_than_off(self, tmp_path, monkeypatch):
        """The removed mode must not silently take the FINDINGS away on upgrade.

        `annotate` used to label the binding objects. It went with the RBAC grant that enabled
        it, because Kubernetes refuses a metadata patch on an RBAC object unless the writer
        already holds everything that object grants — measured, 0 of 4 landed.

        Treating it as unrecognised would land on `off`, and a cluster that had it set would
        stop reporting findings entirely after an upgrade. The discovery was always the
        valuable half and never needed the write, so it degrades to `log`, which publishes the
        same findings with no write access. Both spellings, since neither is a typo.
        """
        base = (tmp_path / "c.yaml")
        base.write_text("clusters:\n  - name: c\n    apiUrl: https://x\n    tokenEnv: T\n")
        for spelling in ("annotate", "ANNOTATE", "  annotate  "):
            monkeypatch.setenv("GSD_UNMANAGED_AUDIT_MODE", spelling)
            assert load_settings(str(base)).unmanaged_audit_mode == "log", spelling

    def test_the_default_is_off(self):
        assert Settings().unmanaged_audit_mode == "off"


class TestEvidenceIsSelfContained:
    """A discovery line must stand alone as evidence.

    The log used to read "WOULD stamp ClusterRoleBinding -/demo-cluster-admin-crb": it named
    the object, said nothing about why it mattered, and framed the whole thing as a rehearsal
    for a write that can never land on a normal cluster. The plan now carries what makes each
    object a finding, so the line is actionable without opening the dashboard.
    """

    def test_evidence_names_the_role_and_the_group(self):
        plan = plan_audit_stamps([
            _row("demo-crb", kind="ClusterRoleBinding", ns="",
                 role="cluster-admin", group="app-ocp-rbac-demo"),
        ])
        key = ("ClusterRoleBinding", "", "demo-crb")
        assert plan.stamp == [key]
        assert plan.evidence[key]["role"] == "cluster-admin"
        assert plan.evidence[key]["groups"] == ["app-ocp-rbac-demo"]

    def test_only_the_unmanaged_group_is_evidence(self):
        """The subtle one. A binding can name two groups and be unmanaged for only one.

        Citing the managed group would send a reader to inspect a grant that is fine, and
        leave the actual finding unnamed.
        """
        plan = plan_audit_stamps([
            _row("two-groups", finding="unmanaged", group="hand-made-group"),
            _row("two-groups", finding="ok", group="policy-managed-group"),
        ])
        key = ("RoleBinding", "ns-a", "two-groups")
        assert plan.evidence[key]["groups"] == ["hand-made-group"], (
            "a managed group must never be cited as evidence of being unmanaged"
        )

    def test_every_planned_object_has_evidence(self):
        """The caller must never have to guess whether a key is present."""
        plan = plan_audit_stamps([
            _row("new", finding="unmanaged"),
            _row("adopted", finding="ok", stamped=True, ns="ns-b"),
        ])
        assert plan.stamp and plan.unstamp
        for key in plan.stamp + plan.unstamp:
            assert key in plan.evidence, f"{key} planned with no evidence"

    def test_evidence_survives_the_cap(self):
        """A capped plan still explains the objects it did list."""
        plan = plan_audit_stamps(
            [_row("rb", ns=f"ns-{i:02d}", role="edit", group=f"g-{i}") for i in range(30)],
            max_per_cycle=5,
        )
        assert len(plan.stamp) == 5 and plan.capped == 25
        assert all(plan.evidence[k]["role"] == "edit" for k in plan.stamp)
