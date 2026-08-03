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
         group="app-ocp-rbac-team-ns-admin"):
    return {"binding_kind": kind, "binding_namespace": ns, "binding_name": name,
            "group_name": group, "finding": finding, "audit_stamped": stamped}


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
    def test_the_mode_fails_safe_to_off(self, tmp_path, monkeypatch):
        """A typo must never be the thing that turns on the write path."""
        base = (tmp_path / "c.yaml")
        base.write_text("clusters:\n  - name: c\n    apiUrl: https://x\n    tokenEnv: T\n")
        # "ANNOTATE"/" annotate " are unambiguous spellings, not typos, and parse as
        # annotate. The fail-safe list is words that MEAN something else or nothing.
        for bad in ("on", "true", "yes", "enable", "anotate", "logg"):
            monkeypatch.setenv("GSD_UNMANAGED_AUDIT_MODE", bad)
            assert load_settings(str(base)).unmanaged_audit_mode == "off", bad
        monkeypatch.setenv("GSD_UNMANAGED_AUDIT_MODE", "annotate")
        assert load_settings(str(base)).unmanaged_audit_mode == "annotate"

    def test_the_default_is_off(self):
        assert Settings().unmanaged_audit_mode == "off"


class TestI1WriteSet:
    def test_the_stamp_patch_touches_only_the_three_owned_keys(self):
        """Captured from the real client method via a transport spy: metadata only, and
        only the dashboard's own label and two annotations. Never subjects, never roleRef."""
        import httpx
        from gsd.config import ClusterConfig
        from gsd.kube import ClusterClient

        captured = {}

        def handler(request):
            captured["path"] = str(request.url.path)
            captured["body"] = request.read().decode()
            captured["content_type"] = request.headers.get("content-type")
            return httpx.Response(200, json={})

        client = ClusterClient(ClusterConfig("c", "https://x", token_env="T"))
        # Substitute the transport underneath the real client factory.
        import gsd.kube as kube_mod
        original = client._client
        client._client = lambda: httpx.Client(
            transport=httpx.MockTransport(handler), base_url="https://x"
        )
        client.stamp_unmanaged_binding("RoleBinding", "ns-a", "hand-made",
                                       "2026-08-02T20:00:00Z")
        import json
        body = json.loads(captured["body"])
        assert set(body) == {"metadata"}, "the patch reached outside metadata"
        assert set(body["metadata"]) == {"labels", "annotations"}
        assert body["metadata"]["labels"] == {UNMANAGED_LABEL: "true"}
        assert set(body["metadata"]["annotations"]) == {
            UNMANAGED_DETECTED_AT_ANNOTATION, UNMANAGED_DETECTED_BY_ANNOTATION,
        }
        assert captured["content_type"] == "application/merge-patch+json"
        assert captured["path"].endswith("/namespaces/ns-a/rolebindings/hand-made")

    def test_the_heal_patch_removes_only_the_label(self):
        import httpx, json
        from gsd.config import ClusterConfig
        from gsd.kube import ClusterClient

        captured = {}

        def handler(request):
            captured["body"] = request.read().decode()
            captured["path"] = str(request.url.path)
            return httpx.Response(200, json={})

        client = ClusterClient(ClusterConfig("c", "https://x", token_env="T"))
        client._client = lambda: httpx.Client(
            transport=httpx.MockTransport(handler), base_url="https://x"
        )
        client.unstamp_unmanaged_binding("ClusterRoleBinding", "", "hand-made-crb")
        body = json.loads(captured["body"])
        assert body == {"metadata": {"labels": {UNMANAGED_LABEL: None}}}, (
            "healing must delete the label and touch nothing else — the detected-at "
            "annotations are the audit history and stay"
        )
        assert captured["path"].endswith("/clusterrolebindings/hand-made-crb")

class TestForbiddenIsDiagnosable:
    """The two 403s must not read alike, because they need opposite responses.

    MEASURED on a live cluster with the patch grant correctly in place: every stamp failed and
    the message said the token lacked patch, while `oc auth can-i patch clusterrolebindings
    --as=<the SA>` answered **yes**. An operator following that message would add a grant they
    already had and still see failures.

    The real cause was privilege-escalation prevention — Kubernetes requires a writer of an
    RBAC object to already hold every permission that object grants, even for a metadata-only
    patch — which no amount of `patch` can satisfy.
    """

    @staticmethod
    def _patch(monkeypatch, status: int, body: str):
        import httpx

        from gsd import kube

        class _Resp:
            status_code = status
            text = body

        class _Client:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def patch(self, *a, **kw): return _Resp()

        client = kube.ClusterClient.__new__(kube.ClusterClient)
        monkeypatch.setattr(client, "_client", lambda: _Client(), raising=False)
        return client

    def test_escalation_prevention_says_so_and_does_not_blame_the_grant(self, monkeypatch):
        from gsd.kube import ClusterError

        body = ('clusterrolebindings.rbac.authorization.k8s.io "x" is forbidden: user "y" '
                'is attempting to grant RBAC permissions not currently held: '
                '{APIGroups:[""], Resources:["bindings"], Verbs:["get"]}')
        client = self._patch(monkeypatch, 403, body)
        with pytest.raises(ClusterError) as caught:
            client.stamp_unmanaged_binding("ClusterRoleBinding", "", "x", "2026-01-01T00:00:00Z")
        detail = str(caught.value)
        assert "ESCALATION" in detail.upper(), detail
        assert "lacks patch" not in detail, (
            "still blaming the grant, which the operator already has"
        )

    def test_a_genuinely_missing_grant_still_says_to_check_the_grant(self, monkeypatch):
        from gsd.kube import ClusterError

        client = self._patch(monkeypatch, 403,
                             'clusterrolebindings.rbac.authorization.k8s.io is forbidden: '
                             'User cannot patch resource')
        with pytest.raises(ClusterError) as caught:
            client.stamp_unmanaged_binding("ClusterRoleBinding", "", "x", "2026-01-01T00:00:00Z")
        detail = str(caught.value)
        assert "lacks patch" in detail, detail
        assert "oc auth can-i" in detail, "no way to check it is offered"
