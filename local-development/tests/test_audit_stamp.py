"""The unmanaged-grant discovery invariants, one test per design clause.

docs/unmanaged-audit-design.md is the spec; this file is its enforcement. The decisions live
in a pure module (gsd/audit.py) so every invariant is a plain assertion with no cluster and
no I/O in the way.

`StampPlan`/`stamp`/`unstamp` are the names of a removed write path — they mean "found" and
"no longer found". Nothing here writes to a cluster.
"""

from __future__ import annotations

import pytest

from gsd.audit import plan_audit_stamps
from gsd.config import Settings, load_settings
from gsd.kube import UNMANAGED_LABEL


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


class TestTheSummaryLineReportsTheTrueTotal:
    """The headline number is the size of the problem, not the size of the log burst.

    `plan_audit_stamps` truncates `stamp` to `maxPerCycle` (audit.py:75-77) and the poller used
    to log `len(plan.stamp)` as "N outside the policy system". So a cluster with 500 unmanaged
    grants and the default cap of 20 reported twenty — understating a governance finding 25x in
    the one line an operator reads first and escalates on. The remainder was present, but only
    as an appended clause the reader had to add up.

    `charts/group-sync-dashboard/values.yaml` promised "the summary line always reports the true
    total" while the code did not, which is how this was found.

    SCOPE: the number is every finding awaiting acknowledgement, which is not the cluster total —
    an object already carrying the `rbac.ocp.io/unmanaged` label is a finding but is not
    re-announced (`audit.py:73`). This fixture applies no labels, so here the two coincide.
    """

    CAP = 5
    UNMANAGED = 12          # deliberately > CAP, so listed != total
    EXPECTED_HELD = UNMANAGED - CAP

    @pytest.fixture()
    def caplog_summary(self, tmp_path, monkeypatch, caplog):
        """Run one real refresh_bindings against a fake cluster and return the log text."""
        import types

        from gsd import poller
        from gsd.config import ClusterConfig
        from gsd.store import Store
        from gsd.timeutil import now_iso

        store = Store(str(tmp_path / "t.db"))
        store.upsert_cluster("c1", "https://x", True)
        now = now_iso()

        names = [f"grp-{i}" for i in range(self.UNMANAGED)]
        store.replace_group_state(
            "c1",
            [{"name": n, "member_count": 1, "sync_provider": "gs_ldap",
              "group_synced_at": now, "ldap_uid": None} for n in names + ["managed-grp"]],
            now,
        )
        # Operator-synced, which is half of what makes a hand-made binding a finding.
        store.record_managed_groups(
            "c1", [{"name": n, "sync_provider": "gs_ldap"} for n in names + ["managed-grp"]],
            now,
        )

        def binding(name, group, managed_source=None):
            return types.SimpleNamespace(
                binding_kind="RoleBinding", binding_namespace="ns", binding_name=name,
                role_kind="ClusterRole", role_name="admin", group_name=group,
                managed_source=managed_source, exception=None,
            )

        # One managed binding is REQUIRED: `unmanaged` is gated on the policy operator being
        # in use at all (store.py `EXISTS (... m.managed_source IS NOT NULL)`), so without
        # this row every binding classifies `ok` and the test would pass vacuously at zero.
        rows = [binding("managed", "managed-grp", managed_source="policy")]
        rows += [binding(f"hand-made-{i}", n) for i, n in enumerate(names)]

        class FakeClient:
            def __init__(self, *a, **kw): pass
            def fetch_bindings(self): return rows
            def fetch_user_bindings(self): return []
            def fetch_operator_configs(self): return None

        monkeypatch.setattr(poller, "ClusterClient", FakeClient)
        with caplog.at_level("INFO", logger="gsd.poller"):
            poller.refresh_bindings(
                store, ClusterConfig("c1", "https://x", token_env="T"), timeout=5,
                audit_mode="log", audit_max_per_cycle=self.CAP,
            )
        return caplog.text

    def test_the_headline_number_is_every_finding_not_just_the_listed_ones(
            self, caplog_summary):
        assert f"{self.UNMANAGED} outside the policy system" in caplog_summary, (
            "the summary must report every finding on the cluster; got:\n" + caplog_summary
        )
        assert f"{self.CAP} outside the policy system" not in caplog_summary, (
            "the headline is the capped count again — the defect is back"
        )

    def test_the_capped_remainder_is_still_declared(self, caplog_summary):
        """A total the reader cannot reconcile against the lines below it invites distrust."""
        assert f"{self.CAP} listed below" in caplog_summary
        assert f"{self.EXPECTED_HELD} held back" in caplog_summary

    def test_exactly_the_cap_is_listed_individually(self, caplog_summary):
        listed = caplog_summary.count("UNMANAGED GRANT DISCOVERED")
        assert listed == self.CAP, f"expected {self.CAP} individual findings, got {listed}"
