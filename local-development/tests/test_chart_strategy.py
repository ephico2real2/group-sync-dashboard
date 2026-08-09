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

import yaml

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


def _proxy_args(out: str) -> list[str]:
    """The oauth-proxy container's args, as a list of flag strings.

    ARG LINES ONLY, never a substring search of the manifest — and that distinction has already
    caught one wrong assertion. Comments in a Helm template are YAML comments, so they are
    EMITTED into the rendered output; a grep for "cookie-refresh" matches the comment that
    explains its absence and reports the opposite of the truth.
    """
    args, seen_proxy = [], False
    for line in out.splitlines():
        stripped = line.strip()
        if stripped == "- name: oauth-proxy":
            seen_proxy = True
        elif seen_proxy and stripped.startswith("- name: "):
            break                      # a later container; the proxy's args are done
        elif seen_proxy and stripped.startswith("- -"):
            args.append(stripped[2:])
    return args


def _config_data(out: str) -> dict:
    """The ConfigMap's clusters.yaml body, parsed.

    Parsed rather than grepped so an assertion about a VALUE reads the value, and an assertion
    about a key being absent cannot be satisfied by the key appearing in a comment — the
    rendered manifest carries this chart's explanatory comments, so a substring search over it
    answers the wrong question.
    """
    lines, inside = [], False
    for line in out.splitlines():
        if line.strip().startswith("clusters.yaml:"):
            inside = True
            continue
        if inside:
            if line and not line.startswith("    "):
                break
            lines.append(line[4:] if line.startswith("    ") else line)
    return yaml.safe_load("\n".join(lines)) or {}


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


class TestLoginCaptureReadsOneNamespaceOnly:
    """The dashboard's log read, and the one thing that must never widen.

    `pods/log` in a ClusterRole is EVERY POD ON THE CLUSTER — tokens, connection strings, customer
    data. That is a far wider grant than the group and binding reads this dashboard exists for, so the
    read is a Role in the single namespace whose logs it parses.
    """

    ON = {"loginCapture__enabled": "true"}

    def _docs(self, out):
        import yaml
        return [d for d in yaml.safe_load_all(out) if d]

    def test_nothing_renders_by_default(self):
        ok, out = render()
        assert ok, out
        assert "login-capture" not in out, "the log read renders without being enabled"

    def test_the_log_read_is_never_cluster_scoped(self):
        """The whole point. A ClusterRole here reads every pod's logs on the cluster."""
        for extra in ({}, self.ON, {**self.ON, "authLogLevel__manage": "true"}):
            ok, out = render(**extra)
            assert ok, out
            for d in self._docs(out):
                if d.get("kind") != "ClusterRole":
                    continue
                for rule in d.get("rules") or []:
                    res = rule.get("resources") or []
                    assert "pods/log" not in res and "pods" not in res, (
                        f"settings={extra}: {d['metadata']['name']} grants {res} CLUSTER-WIDE. "
                        f"pods/log in a ClusterRole reads every pod on the cluster — it must stay a "
                        f"Role in loginCapture.namespace."
                    )

    def test_it_grants_exactly_list_pods_and_get_logs(self):
        """Both verbs are needed and neither is enough: there is no Deployment log subresource
        (verified: GET .../deployments/oauth-openshift/log -> "could not find the requested
        resource"), so pods must be LISTED to be discovered and then read one at a time."""
        ok, out = render(**self.ON)
        assert ok, out
        role = [d for d in self._docs(out)
                if d.get("kind") == "Role" and "login-capture" in d["metadata"]["name"]][0]
        assert role["metadata"]["namespace"] == "openshift-authentication"
        got = sorted((tuple(r["resources"]), tuple(sorted(r["verbs"]))) for r in role["rules"])
        assert got == [(("pods",), ("list",)), (("pods/log",), ("get",))], (
            f"the log read changed: {got}. No write verb belongs here at any value."
        )

    def test_the_read_binds_to_the_dashboard_not_the_job_identity(self):
        """This one IS the dashboard's own ServiceAccount — it is a read. The inverse of the
        log-level Jobs, whose write must never reach it."""
        ok, out = render(**self.ON)
        assert ok, out
        rb = [d for d in self._docs(out)
              if d.get("kind") == "RoleBinding" and "login-capture" in d["metadata"]["name"]][0]
        subj = rb["subjects"][0]
        assert subj["kind"] == "ServiceAccount"
        assert "auth-loglevel" not in subj["name"], (
            "the read must not be granted to the log-level Job's write identity"
        )
        assert subj.get("namespace"), "an unnamespaced subject binds nothing"


class TestTheOauthLogLevelJobKeepsTheWriteOffTheDashboard:
    """The chart's only write grant, and the whole point is WHERE it lives.

    Enabling login capture needs `patch` on authentications.operator.openshift.io — a write to a core
    platform object. `rbac.yaml` states "NO WRITE VERB ON ANYTHING THE DASHBOARD REPORTS ON" and five
    documents cite that line, so the grant sits on a ServiceAccount used only by the hook Jobs and
    the dashboard's own role stays read-only. These tests are what stop that separation eroding.

    NOTE ON PLACEMENT: `.github/workflows/ci.yml` points the `chart` job at THIS FILE by name.
    """

    ON = {"authLogLevel__manage": "true"}

    def _docs(self, out):
        import yaml
        return [d for d in yaml.safe_load_all(out) if d]

    def test_nothing_renders_by_default(self):
        """The chart must not touch a cluster's authentication config unless asked."""
        ok, out = render()
        assert ok, out
        assert "auth-loglevel" not in out, "the log-level Job renders without being enabled"

    def test_the_dashboards_own_role_never_gains_the_write(self):
        """The invariant. If this fails, five documents became false."""
        for extra in ({}, self.ON, {**self.ON, "authLogLevel__enabled": "true"}):
            ok, out = render(**extra)
            assert ok, out
            for d in self._docs(out):
                if d.get("kind") != "ClusterRole":
                    continue
                if "auth-loglevel" in d["metadata"]["name"]:
                    continue                      # the Job's own role, which is allowed to write
                for rule in d.get("rules") or []:
                    writes = set(rule.get("verbs") or []) & {
                        "patch", "update", "create", "delete", "deletecollection", "*"}
                    if writes:
                        assert set(rule.get("resources") or []) == {"leases"}, (
                            f"settings={extra}: the DASHBOARD's role gained {sorted(writes)} on "
                            f"{rule.get('resources')}. The log-level write belongs on the Job's own "
                            f"ServiceAccount — see rbac.yaml's header and "
                            f"docs/reference-architecture.md."
                        )

    def test_the_jobs_write_is_pinned_to_one_named_object(self):
        """Unpinned, this would be patch on every object in operator.openshift.io — which includes
        the cluster's entire authentication configuration. resourceNames IS honoured for `patch`,
        unlike `create`/`list` where the name is not in the request path."""
        ok, out = render(**self.ON)
        assert ok, out
        rules = [r for d in self._docs(out)
                 if d.get("kind") == "ClusterRole" and "auth-loglevel" in d["metadata"]["name"]
                 for r in d["rules"]
                 if "authentications" in (r.get("resources") or [])]
        assert len(rules) == 1, f"expected exactly one authentications rule, got {len(rules)}"
        rule = rules[0]
        assert rule.get("resourceNames") == ["cluster"], (
            f"the write must be pinned to the single named object: {rule}"
        )
        assert sorted(rule["verbs"]) == ["get", "patch"], (
            f"only get and patch — no update, no list, no watch: {rule['verbs']}"
        )

    def test_the_job_applies_the_REQUESTED_level_both_ways(self):
        """Two switches, and the Job runs for both values of `enabled`.

        Helm does not run a Job you merely stopped rendering, so a one-way enable Job would strand
        the cluster in Debug the moment somebody flipped the flag back and saw nothing happen.

        Asserts the PATCH PAYLOAD, not the WANT assignment. Pinning `WANT=` alone was a false
        guarantee: a Job that assigns WANT and then hardcodes `logLevel: Debug` in the patch passed.
        """
        for enabled, level, other in (("false", "Normal", "Debug"), ("true", "Debug", "Normal")):
            ok, out = render(**self.ON, authLogLevel__enabled=enabled)
            assert ok, out
            job = [d for d in self._docs(out)
                   if d.get("kind") == "Job" and not d["metadata"]["name"].endswith("-revert")][0]
            script = job["spec"]["template"]["spec"]["containers"][0]["command"][-1]
            assert f"WANT={level}" in script, f"enabled={enabled} must request {level}"
            # The patch must interpolate WANT rather than name a level literally.
            assert '\\"logLevel\\":\\"${WANT}\\"' in script, (
                f"enabled={enabled}: the patch must use ${{WANT}}, or the toggle is one-way"
            )
            assert f'logLevel\\":\\"{other}' not in script, (
                f"enabled={enabled}: a hardcoded {other} in the patch defeats the toggle"
            )

    def test_the_revert_job_patches_Normal_and_only_Normal(self):
        """B5: nothing pinned the revert Job's payload, so a revert that patched `Debug` passed —
        which would make `helm uninstall` ENABLE debug logging on the way out."""
        ok, out = render(**self.ON)
        assert ok, out
        job = [d for d in self._docs(out)
               if d.get("kind") == "Job" and d["metadata"]["name"].endswith("-revert")][0]
        script = job["spec"]["template"]["spec"]["containers"][0]["command"][-1]
        assert '"logLevel":"Normal"' in script, "the revert Job must patch Normal"
        assert '"logLevel":"Debug"' not in script, "the revert Job must never patch Debug"

    def test_the_write_binding_names_the_jobs_own_service_account(self):
        """B1, and the most important test here: the invariant was only HALF guarded.

        The ClusterRole was tested; its BINDING was not. Rebinding the write role to the dashboard's
        ServiceAccount passed all 30 tests while the chart README claimed the suite would fail. The
        full subject triple is asserted — dropping the namespace let `other-namespace` through.
        """
        ok, out = render(**self.ON)
        assert ok, out
        binding = [d for d in self._docs(out)
                   if d.get("kind") == "ClusterRoleBinding"
                   and "auth-loglevel" in d["metadata"]["name"]][0]
        subjects = binding["subjects"]
        assert len(subjects) == 1, f"exactly one subject, got {subjects}"
        s = subjects[0]
        assert (s["kind"], s["name"]) == ("ServiceAccount", "t-group-sync-dashboard-auth-loglevel"), (
            f"the write must bind to the JOB's ServiceAccount, not {s}. If this fails, the dashboard "
            f"may be able to patch the cluster's authentication config."
        )
        assert s.get("namespace"), "an unnamespaced ServiceAccount subject binds nothing"
        assert binding["roleRef"]["name"] == "t-group-sync-dashboard-auth-loglevel"

    def test_a_service_account_name_collision_is_refused(self):
        """The configuration-level bypass Codex found: setting serviceAccount.name to the Job's SA
        name renders two same-named ServiceAccounts, runs the DASHBOARD as that identity, and hands
        it the patch grant. Verified before the guard: it rendered cleanly."""
        ok, out = render(**self.ON,
                         serviceAccount__name="t-group-sync-dashboard-auth-loglevel")
        assert not ok, "the chart rendered a configuration that gives the dashboard the write grant"
        assert "collides with the log-level Job" in out

    def test_the_set_jobs_hook_annotations_are_pinned(self):
        """B6: stripping them made the Job an ordinary object, which then FAILS every later upgrade
        on an immutable-field conflict — and nothing caught it."""
        ok, out = render(**self.ON)
        assert ok, out
        job = [d for d in self._docs(out)
               if d.get("kind") == "Job" and not d["metadata"]["name"].endswith("-revert")][0]
        ann = job["metadata"].get("annotations") or {}
        assert ann.get("helm.sh/hook") == "post-install,post-upgrade", (
            f"the set Job must be a hook, or it becomes a permanent object: {ann}"
        )
        assert "before-hook-creation" in (ann.get("helm.sh/hook-delete-policy") or ""), (
            "without before-hook-creation, the second upgrade fails on the existing Job's name"
        )

    def test_the_job_role_grants_nothing_beyond_its_two_rules(self):
        """B7: the role's total surface was unbounded — an extra rule or a widened apiGroup rode
        through every test. Pinned exhaustively, so widening it is a deliberate act."""
        ok, out = render(**self.ON)
        assert ok, out
        role = [d for d in self._docs(out)
                if d.get("kind") == "ClusterRole" and "auth-loglevel" in d["metadata"]["name"]][0]
        got = sorted(
            (tuple(sorted(r["apiGroups"])), tuple(sorted(r["resources"])),
             tuple(sorted(r.get("resourceNames") or [])), tuple(sorted(r["verbs"])))
            for r in role["rules"]
        )
        assert got == sorted([
            (("operator.openshift.io",), ("authentications",), ("cluster",), ("get", "patch")),
            (("apps",), ("deployments",), ("oauth-openshift",), ("get",)),
        ]), f"the Job's role changed. Every rule here is a cluster-scoped grant: {got}"

    def test_the_patched_object_is_the_operator_cr_and_says_so(self):
        """Three cluster-scoped objects have confusingly similar names, and two are one word apart:

            authentications.operator.openshift.io/cluster   spec.logLevel        <- what we patch
            authentications.config.openshift.io/cluster     spec.type, ...
            oauth.config.openshift.io/cluster               spec.identityProviders  ("the OAuth CR")

        Calling ours "the OAuth CR" points a reader at the object that holds the identity providers —
        which this feature never touches — and makes the RBAC look wrong. Verified on a live cluster.
        """
        ok, out = render(**self.ON)
        assert ok, out
        for job in [d for d in self._docs(out)
                    if d.get("kind") == "Job" and "auth-loglevel" in d["metadata"]["name"]]:
            script = job["spec"]["template"]["spec"]["containers"][0]["command"][-1]
            assert "authentications.operator.openshift.io cluster" in script, (
                f"{job['metadata']['name']} no longer targets the operator CR"
            )
            assert "oauth.config.openshift.io" not in script, (
                "this feature must never touch the OAuth CR — it holds the identity providers"
            )
            assert "operatorLogLevel" not in script, (
                "operatorLogLevel is the OPERATOR's own verbosity; the login lines come from the "
                "operand, whose verbosity is spec.logLevel"
            )
        role = [d for d in self._docs(out)
                if d.get("kind") == "ClusterRole" and "auth-loglevel" in d["metadata"]["name"]][0]
        groups = {g for r in role["rules"] for g in r["apiGroups"]}
        assert "config.openshift.io" not in groups, (
            "the grant must not reach config.openshift.io — that is where the OAuth CR and the "
            "Authentication CONFIG CR live"
        )

    def test_the_outage_warning_survives(self):
        """C1: the behaviour is inherent to a logLevel change; the WARNING is the deliverable.

        Measured on a 1-replica cluster: `authentication` reported "no oauth-openshift pods available
        on any node" and a second application logged HTTP 503 on the groups API while it rolled.
        """
        ok, out = render(**self.ON)
        assert ok, out
        assert "LOGIN OUTAGE" in out, "the Job no longer warns that a 1-replica roll is an outage"
        values = (CHART / "values.yaml").read_text()
        assert "LOGIN OUTAGE" in values.upper(), "values.yaml no longer warns at the decision point"

    def test_the_image_is_not_a_credentialed_registry(self):
        """C2: registry.redhat.io needs a pull secret this chart does not create, and the failure
        mode is a FAILED RELEASE — measured ErrImagePull -> `helm upgrade` failed "context canceled".
        """
        ok, out = render(**self.ON)
        assert ok, out
        # Scoped to THIS feature's Jobs: the oauth-proxy legitimately uses registry.redhat.io and is
        # out of scope. A whole-render assertion matched that and failed for the wrong reason.
        for job in [d for d in self._docs(out)
                    if d.get("kind") == "Job" and "auth-loglevel" in d["metadata"]["name"]]:
            image = job["spec"]["template"]["spec"]["containers"][0]["image"]
            assert "registry.redhat.io" not in image, (
                f"{job['metadata']['name']} uses {image}, which needs a pull secret this chart does "
                f"not create. Measured: ErrImagePull -> `helm upgrade` failed with context canceled."
            )

    def test_a_wait_longer_than_the_deadline_is_refused(self):
        """A6/B2: the deadline would kill the Job mid-wait and fail `helm upgrade`, contradicting the
        documented promise that a wait timeout is not a failure."""
        ok, out = render(**self.ON, authLogLevel__waitSeconds="600")
        assert not ok, "a wait longer than the deadline rendered happily"
        assert "must be LESS than activeDeadlineSeconds" in out

    def test_the_wait_gates_on_the_operands_own_flag(self):
        """A1: generation/replica polling is a steady-state invariant, equally true BEFORE the
        operator reconciles — it logged "rollout complete: generation 26" while the deployment went
        on to 27, with the new pod starting 29s after the Job exited. `--v=<n>` in the Deployment's
        container args can only appear once the level is rendered into the workload."""
        ok, out = render(**self.ON)
        assert ok, out
        job = [d for d in self._docs(out)
               if d.get("kind") == "Job" and not d["metadata"]["name"].endswith("-revert")][0]
        script = job["spec"]["template"]["spec"]["containers"][0]["command"][-1]
        # Pins the GATE, not a mention. An earlier version of this test asserted only that
        # `--v=${WANT_V}` appeared somewhere in the script — and it survived a mutation that broke the
        # case pattern, because the string still appeared in an echo. Mutation-tested: this fails when
        # the match pattern changes.
        assert '*"--v=${WANT_V}"*)' in script, (
            "the wait no longer MATCHES on the operand's verbosity flag — a mention in an echo is "
            "not a gate"
        )
        assert "WANT_V=4" in script and "WANT_V=2" in script, "Debug=4 / Normal=2 mapping is gone"

    def test_uninstall_reverts_by_default(self):
        """Without this, removing the dashboard leaves the OAuth server naming every person who
        authenticates, with nothing left watching the logs and nobody aware of it."""
        ok, out = render(**self.ON)
        assert ok, out
        jobs = [d for d in self._docs(out)
                if d.get("kind") == "Job" and d["metadata"]["name"].endswith("-revert")]
        assert len(jobs) == 1, "the pre-delete revert Job is missing"
        ann = jobs[0]["metadata"]["annotations"]
        assert ann["helm.sh/hook"] == "pre-delete", (
            "must be pre-delete: post-delete would run after Helm removed the ServiceAccount it "
            "authenticates with"
        )

    def test_neither_job_carries_a_keep_policy(self):
        """`helm.sh/resource-policy: keep` on the SA or binding would orphan a CLUSTER-SCOPED RBAC
        pair on every uninstall, forever. It is not needed: Helm runs pre-delete hooks before it
        deletes release resources, so both still exist when the revert Job runs."""
        ok, out = render(**self.ON)
        assert ok, out
        for d in self._docs(out):
            if "auth-loglevel" not in (d.get("metadata", {}).get("name") or ""):
                continue
            ann = d["metadata"].get("annotations") or {}
            assert "helm.sh/resource-policy" not in ann, (
                f"{d['kind']} {d['metadata']['name']} would be orphaned on uninstall"
            )


class TestTheUsersGrantIsReadOnlyAndOptional:
    """The `users` grant exists for one field, `fullName`, and must stay the smallest thing that
    buys it.

    A User object carries identities and group membership as well as a display name, and the read
    is cluster-wide — every account on the cluster, not just group members. So `get`/`list` and
    nothing else, and it has to remain switchable off: an operator who will not grant a read over
    every identity on the cluster should lose display names and keep the dashboard.

    NOTE ON PLACEMENT: like the class below, this lives here because `.github/workflows/ci.yml`
    points the `chart` job at THIS FILE by name. A chart-rendering test in any other module is not
    run by that job.
    """

    def _users_rules(self, out):
        import yaml
        found = []
        for doc in yaml.safe_load_all(out):
            if doc and doc.get("kind") in ("ClusterRole", "Role"):
                for rule in doc.get("rules") or []:
                    if "users" in (rule.get("resources") or []):
                        found.append(rule)
        return found

    def test_granted_by_default_and_read_only(self):
        ok, out = render()
        assert ok, out
        rules = self._users_rules(out)
        assert len(rules) == 1, f"expected exactly one users rule, got {len(rules)}"
        rule = rules[0]
        assert rule["apiGroups"] == ["user.openshift.io"]
        assert sorted(rule["verbs"]) == ["get", "list"], (
            f"the users grant must be read-only and must not add watch: {rule['verbs']}. "
            f"If that changed deliberately, update rbac.yaml's header, values.yaml, the chart "
            f"README and docs/reference-architecture.md in the same commit."
        )

    def test_declining_the_grant_drops_the_rule_and_keeps_the_rest(self):
        """rbac.users=false must cost display names only — the group data must survive."""
        ok, out = render(rbac__users="false")
        assert ok, out
        assert self._users_rules(out) == [], "rbac.users=false still grants users"
        import yaml
        groups_granted = any(
            "groups" in (rule.get("resources") or [])
            for doc in yaml.safe_load_all(out)
            if doc and doc.get("kind") == "ClusterRole"
            for rule in doc.get("rules") or []
        )
        assert groups_granted, "declining the users grant must not disturb the groups grant"

    def test_users_is_never_granted_when_rbac_is_off_entirely(self):
        ok, out = render(rbac__create="false")
        assert ok, out
        assert self._users_rules(out) == []


class TestTheProxyTrustsTheSameCAsTheApp:
    """The oauth-proxy needs the corporate CA too, and for a while only the app got it.

    MEASURED on a corporate cluster whose *.apps wildcard is signed by an internal CA. Login
    returned `500 Internal Error` with a healthy pod, a valid Route and correct RBAC:

        provider.go:631   Performing OAuth discovery against https://172.31.0.1/...
        provider.go:671   200 GET https://172.31.0.1/.well-known/oauth-authorization-server
        oauthproxy.go:661 error redeeming code: Post
            "https://oauth-openshift.apps.ocp4.company.net/oauth/token":
            tls: failed to verify certificate: x509: certificate signed by unknown authority

    Discovery SUCCEEDS and redemption FAILS, and that asymmetry is the whole bug. Discovery
    goes to the in-cluster API address, which the ServiceAccount CA covers. Discovery then
    returns the PUBLIC issuer, so the code exchange goes to the ingress-served OAuth route,
    signed by a CA the ServiceAccount bundle knows nothing about.

    The chart already had the bundles. They reached `GSD_TRUSTED_CA_FILE` and nothing else, so
    the dashboard could poll a corporate-signed cluster while nobody could log in to read the
    result — the failure was in the half nobody had wired up.

    NOTE ON PLACEMENT: this lives here because `.github/workflows/ci.yml` points the `chart`
    job at THIS FILE by name. A chart-rendering test in any other module is not run by that
    job, and the `tests` job skips these for want of a helm binary.
    """

    CA_ARG = "-openshift-ca="
    SA_CA = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"

    def _proxy(self, **values):
        import yaml
        ok, out = render(**values)
        assert ok, f"failed to render with {values}:\n{out}"
        for doc in yaml.safe_load_all(out):
            if doc and doc.get("kind") == "Deployment":
                spec = doc["spec"]["template"]["spec"]
                proxy = next((c for c in spec["containers"] if c["name"] == "oauth-proxy"), None)
                assert proxy, "the oauth-proxy container did not render"
                return proxy, spec
        raise AssertionError("no Deployment in the rendered output")

    def test_the_service_account_ca_is_still_passed_explicitly(self):
        """Passing any -openshift-ca REPLACES the flag's default, so this cannot be dropped.

        Its own help: "paths to CA roots for the OpenShift API (may be given multiple times,
        defaults to /var/run/secrets/kubernetes.io/serviceaccount/ca.crt)". Losing it breaks
        OAuth DISCOVERY against the in-cluster API address — the half that currently works.
        """
        proxy, _ = self._proxy()
        cas = [a for a in proxy["args"] if a.startswith(self.CA_ARG)]
        assert f"{self.CA_ARG}{self.SA_CA}" in cas, (
            f"the ServiceAccount CA is no longer passed; got {cas}"
        )

    def test_an_enabled_bundle_reaches_the_proxy_and_not_only_the_app(self):
        """The regression itself: bundles configured, app trusts them, proxy does not."""
        for values, expect in (
            ({}, "injected"),                                                  # default
            ({"trustedCA__existingConfigMap__enabled": "true"}, "enterprise"),
        ):
            proxy, _ = self._proxy(**values)
            cas = [a for a in proxy["args"] if a.startswith(self.CA_ARG)]
            assert any(expect in a for a in cas), (
                f"with {values or 'defaults'} the proxy gets {cas} — the {expect} bundle is "
                f"mounted for the dashboard but never handed to the proxy, so login fails on "
                f"any cluster whose OAuth route is signed by that CA"
            )

    def test_every_ca_path_the_proxy_is_given_is_actually_mounted(self):
        """A path the proxy cannot read is worse than no flag: it fails to start.

        Checks the pairing rather than the two halves separately, because they are edited in
        different parts of the template and drift apart silently.
        """
        for values in ({},
                       {"trustedCA__existingConfigMap__enabled": "true"},
                       {"trustedCA__injected__enabled": "false",
                        "trustedCA__existingConfigMap__enabled": "true"},
                       {"trustedCA__injected__enabled": "false"}):
            proxy, _ = self._proxy(**values)
            mounts = [m["mountPath"].rstrip("/") for m in proxy.get("volumeMounts", [])]
            for arg in proxy["args"]:
                if not arg.startswith(self.CA_ARG):
                    continue
                path = arg[len(self.CA_ARG):]
                if path == self.SA_CA:
                    continue          # projected by the kubelet, not by a chart volume
                assert any(path.startswith(m + "/") for m in mounts), (
                    f"with {values or 'defaults'} the proxy is told to read {path} but only "
                    f"mounts {mounts} — the container would fail to start"
                )

    def test_no_volume_mount_names_a_volume_that_does_not_exist(self):
        """Guards the other direction: a mount with no matching volume makes the pod unschedulable.

        Applies to BOTH containers, since the bundles are mounted twice now.
        """
        for values in ({},
                       {"trustedCA__existingConfigMap__enabled": "true"},
                       {"trustedCA__injected__enabled": "false"},
                       {"trustedCA__injected__enabled": "false",
                        "trustedCA__existingConfigMap__enabled": "false"}):
            _, spec = self._proxy(**values)
            volumes = {v["name"] for v in spec.get("volumes", [])}
            for container in spec["containers"]:
                for mount in container.get("volumeMounts", []):
                    assert mount["name"] in volumes, (
                        f"with {values or 'defaults'} container {container['name']} mounts "
                        f"{mount['name']!r}, which is not in {sorted(volumes)}"
                    )


class TestSessionCookieLifetime:
    """-cookie-expire and where its number comes from: Kibana's rule, adapted.

    The cluster's spec.tokenConfig.accessTokenInactivityTimeout WINS when it is set and
    readable at render time; the shipped 4h fallback applies otherwise. `helm template`
    runs with lookup EMPTY by construction, so what CI pins is the degrade branch — the
    fallback, and the flag and the ConfigMap restating one string — plus the guards. The
    CR-wins branch cannot be reached from here (there is no cluster); it was verified by
    server dry-run against the reference cluster and by exercising the helper's branch
    arithmetic on constructed objects, both recorded in the design doc.
    """

    def test_defaults_render_the_absolute_cap_and_no_refresh(self):
        """4h absolute, no -cookie-refresh. Measured on provider=openshift: the proxy's
        refresh-time revalidation sends the token as a query parameter, the API server
        ignores it and answers 403 as system:anonymous, so refresh force-clears the
        session at every interval — a sliding window is not something this provider can
        have. Kibana ships the same shape: expire set, refresh absent."""
        ok, out = render()
        assert ok, out
        args = _proxy_args(out)
        assert "-cookie-expire=4h" in args
        assert not any(a.startswith("-cookie-refresh") for a in args), args

    def test_the_access_token_is_never_forwarded_to_the_app(self):
        """-pass-access-token is absent even with the proxy ON, and its absence is the design.

        It was added so sign-out could revoke the user's token the way the console's does, and
        removed after that was measured failing: the console can revoke because its tokens
        carry scope user:full, while this chart authenticates through a ServiceAccount whose
        tokens carry user:info and user:check-access, so the API answered 403 whatever the RBAC
        said. Re-adding the flag would hand the app a credential able to act as the user
        anywhere on the cluster, buying nothing the proxy's own sign_out does not already do.
        """
        ok, out = render()
        assert ok
        assert "-pass-access-token" not in _proxy_args(out), (
            "the app is being handed a live user credential it has no use for")

    def test_setting_the_retired_refresh_key_is_refused_with_the_measurement(self):
        """An old values file carrying refresh must fail loudly with the reason, or its
        owner believes they have a sliding window while the proxy force-logs-everyone-
        out at that interval."""
        ok, out = render(oauthProxy__cookie__refresh="5m")
        assert not ok, "the retired refresh knob rendered silently as a no-op"
        assert "force-clears" in out and "system:anonymous" in out

    def test_the_off_spelling_of_refresh_is_tolerated(self):
        """refresh: "" in an old values file already matches shipped behaviour, so it is
        not worth failing an upgrade over."""
        ok, out = render(oauthProxy__cookie__refresh="")
        assert ok, out
        assert not any(a.startswith("-cookie-refresh") for a in _proxy_args(out))

    def test_a_nulled_cookie_block_still_renders_the_shipped_fallback(self):
        """A values file with `oauthProxy.cookie: null` must fall back to 4h, not to the
        proxy's built-in 7-day cookie."""
        ok, out = render(oauthProxy__cookie="null")
        assert ok, out
        assert "-cookie-expire=4h" in _proxy_args(out)

    def test_the_configmap_restates_the_flag_string_and_carries_no_refresh_key(self):
        """The session cookie is HttpOnly, so the page can never observe its lifetime —
        the app restates it from this key, rendered by the SAME helper that builds the
        flag, cluster lookup included. sessionCookieRefresh left with the knob; the app
        reads absence as disabled."""
        ok, out = render(oauthProxy__cookie__expire="90m")
        assert ok, out
        assert "-cookie-expire=90m" in _proxy_args(out)
        cfg = _config_data(out)
        assert cfg["sessionCookieExpire"] == "90m"
        assert "sessionCookieRefresh" not in cfg

    def test_a_non_duration_fallback_is_refused_at_render(self):
        """The proxy validates its flag at startup and crash-loops; the render is where
        the operator is still watching. Only the values-supplied fallback needs this —
        the CR field is validated as a duration by the API server itself."""
        for bad in ("4hr", "240", "four hours"):
            ok, out = render(oauthProxy__cookie__expire=bad)
            assert not ok, f"cookie.expire={bad!r} rendered happily and would crash-loop the proxy"
            assert "not a Go duration" in out

    def test_no_proxy_means_no_flags_no_guards_no_session_keys(self):
        """With the sidecar off there is nothing to crash-loop and no session to
        restate: a bad duration must not block a render that never uses it, and the
        ConfigMap must not carry session keys the app would then parse with no render
        guard standing in front of them."""
        ok, out = render(oauthProxy__enabled="false", oauthProxy__cookie__expire="4hr")
        assert ok, out
        assert "-cookie-expire" not in out
        assert "-pass-access-token" not in out
        assert "sessionCookieExpire" not in _config_data(out)

