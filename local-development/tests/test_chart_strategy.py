"""The chart must not render a manifest that puts two processes on one SQLite file.

Codex found the hole these tests close: `replicaCount=1` with an explicit
`strategy=RollingUpdate` rendered perfectly happily. The existing guard only rejected
RollingUpdate against ReadWriteOncePod — the mode where the scheduler refuses the second
pod anyway — while the DEFAULT ReadWriteMany, which mounts twice without complaint, went
straight through. During the rollout the outgoing and incoming pod both open
/data/gsd.db, and WAL corrupts rather than errors when two hosts share it.

These shell out to `helm template` because the guard IS Helm templating; asserting on
rendered output is the only thing that tests what actually ships.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest

CHART = pathlib.Path(__file__).resolve().parents[2] / "charts" / "group-sync-dashboard"

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")


def render(**values):
    """Render the chart. Returns (ok, combined output)."""
    args = ["helm", "template", "t", str(CHART), "--set", "ingress.host=t.example.com"]
    for key, value in values.items():
        args += ["--set", f"{key.replace('__', '.')}={value}"]
    done = subprocess.run(args, capture_output=True, text=True)
    return done.returncode == 0, done.stdout + done.stderr


class TestSingleReplicaRollingUpdate:
    def test_the_case_codex_found_is_now_refused(self):
        """One replica, persistence on, explicit RollingUpdate, default RWX."""
        ok, out = render(replicaCount=1, strategy="RollingUpdate")
        assert not ok, "renders a rollout that puts two pods on one SQLite file"
        assert "two processes on one SQLite file" in out

    def test_refused_for_every_access_mode_not_just_RWOP(self):
        """The original guard keyed on ReadWriteOncePod, which was the SAFE mode here —
        the scheduler refuses the second pod. The permissive modes were the risk."""
        for mode in ("ReadWriteMany", "ReadWriteOnce", "ReadWriteOncePod"):
            ok, _ = render(replicaCount=1, strategy="RollingUpdate",
                           persistence__accessMode=mode)
            assert not ok, f"accessMode={mode} still renders a shared-file rollout"


class TestStillRenders:
    """The guard must not be so broad that it breaks legitimate configurations."""

    def test_defaults(self):
        ok, out = render()
        assert ok, out
        assert "type: Recreate" in out

    def test_explicit_recreate_at_one_replica(self):
        ok, out = render(replicaCount=1, strategy="Recreate")
        assert ok, out

    def test_rollingupdate_above_one_replica_is_correct_and_allowed(self):
        """Each pod owns /data/$POD_NAME/gsd.db up there, so overlap is harmless — and
        Recreate at 3 replicas would take the whole deployment down on every upgrade,
        removing the only reason to scale."""
        ok, out = render(replicaCount=3, leaderElection__enabled=False,
                         strategy="RollingUpdate")
        assert ok, out
        assert "value: /data/$(POD_NAME)/gsd.db" in out

    def test_rollingupdate_at_one_replica_without_persistence(self):
        """No PVC means no shared file: each pod gets its own emptyDir, so an overlapping
        rollout cannot collide. Ephemeral, but not corrupting."""
        ok, out = render(replicaCount=1, strategy="RollingUpdate",
                         persistence__enabled=False)
        assert ok, out

    def test_derived_strategy_above_one_replica_is_rollingupdate(self):
        ok, out = render(replicaCount=2, leaderElection__enabled=False)
        assert ok, out
        assert "type: RollingUpdate" in out


class TestNoPatchVerbAtAnyAuditMode:
    """`docs/unmanaged-audit-design.md` I1 asserted this and said no test enforced it.

    The chart used to grant `patch` on rolebindings/clusterrolebindings when
    `config.unmanagedAudit.mode` was `annotate`, so the dashboard could label its own
    findings. A live cluster measured 0 of 4 labels landing and the API server demanding 175
    additional rule sets to place one, so the mode and the grant were both removed. What
    stops them coming back is this test.

    It PARSES the rendered YAML rather than grepping it. `rbac.yaml` deliberately keeps the
    history of the removed grant in its comments, and Helm emits template comments verbatim —
    three lines of rendered output contain the word `patch` today. A text search would either
    fail on the comments or be written loosely enough to miss a real regression.
    """

    # `annotate` and `bogus` are not valid values; the app downgrades both to `log`. They are
    # here because the RBAC must not depend on the value being valid — a typo in a values file
    # must never be the thing standing between a reader and a write grant.
    MODES = ("off", "log", "annotate", "bogus", "")

    def _rules(self, mode):
        import yaml
        ok, out = render(config__unmanagedAudit__mode=mode)
        assert ok, f"mode={mode!r} failed to render:\n{out}"
        rules = []
        for doc in yaml.safe_load_all(out):
            if doc and doc.get("kind") in ("ClusterRole", "Role"):
                for rule in doc.get("rules") or []:
                    rules.append((doc["metadata"]["name"], rule))
        assert rules, f"mode={mode!r} rendered no Role/ClusterRole rules at all"
        return rules

    @pytest.mark.parametrize("mode", MODES)
    def test_no_write_verb_on_any_rbac_object(self, mode):
        """The specific escalation: write access to the objects that grant access."""
        rbac_resources = {"rolebindings", "clusterrolebindings", "roles", "clusterroles"}
        writes = {"patch", "update", "create", "delete", "deletecollection", "*"}
        for name, rule in self._rules(mode):
            resources = set(rule.get("resources") or [])
            if resources & rbac_resources:
                offending = set(rule.get("verbs") or []) & writes
                assert not offending, (
                    f"mode={mode!r}: ClusterRole {name} grants {sorted(offending)} on "
                    f"{sorted(resources & rbac_resources)} — a reader of RBAC must never be "
                    f"able to edit RBAC"
                )

    @pytest.mark.parametrize("mode", MODES)
    def test_the_only_write_in_the_role_is_the_dashboards_own_lease(self, mode):
        """Guards the claim in the other direction.

        Three documents said the dashboard "writes nothing to any cluster" while the role
        granted create/update on leases. Pinning the Lease as the one permitted write keeps
        both the grant and the sentences describing it honest.
        """
        writes = {"patch", "update", "create", "delete", "deletecollection", "*"}
        for name, rule in self._rules(mode):
            offending = set(rule.get("verbs") or []) & writes
            if offending:
                assert set(rule.get("resources") or []) == {"leases"}, (
                    f"mode={mode!r}: ClusterRole {name} grants {sorted(offending)} on "
                    f"{rule.get('resources')} — the leader-election Lease is the only object "
                    f"this application may write. If that changed deliberately, update "
                    f"rbac.yaml's header, values.yaml, the chart README and "
                    f"docs/reference-architecture.md in the same commit."
                )
