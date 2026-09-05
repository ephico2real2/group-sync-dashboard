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

    def test_it_renders_by_default_and_nothing_renders_when_off(self):
        # On since chart 0.14.0: a namespaced read is inside the on-by-default rule.
        ok, out = render()
        assert ok, out
        assert "login-capture" in out, "the log read is the default since chart 0.14.0"
        ok, out = render(loginCapture__enabled="false")
        assert ok, out
        assert "login-capture" not in out, "the log read renders after being disabled"

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
    """The `users` grant is the Users tab's source and must stay the smallest thing that buys it.

    A User object carries identities and group membership as well as a display name, and the read
    is cluster-wide — every account on the cluster, not just group members. So `get`/`list` and
    nothing else, and it has to remain switchable off: an operator who will not grant a read over
    every identity on the cluster loses the Users tab's rows (the tab says so by name) and keeps
    the rest of the dashboard.

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
        """rbac.users=false must cost the Users tab's rows and display names only — the group data must survive."""
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
        guard standing in front of them.

        visibility.enabled=false is required to reach a proxy-off render AT ALL now, and
        that is the point of the guard rather than a concession to this test: a per-user
        control keyed on X-Forwarded-User cannot work when nothing sets that header, so
        declining it is the only renderable way to run without the proxy. Asserted from the
        other side by TestVisibilityThreading.test_visibility_without_the_proxy_is_refused.
        """
        ok, out = render(oauthProxy__enabled="false", visibility__enabled="false",
                         oauthProxy__cookie__expire="4hr")
        assert ok, out
        assert "-cookie-expire" not in out
        assert "-pass-access-token" not in out
        assert "sessionCookieExpire" not in _config_data(out)


class TestVisibilityThreading:
    """visibility.enabled -> GSD_ENABLE_VIEW_RESTRICTIONS, and the adminSar shape.

    The switch is a security control, so the chart must refuse the states in which it
    silently cannot work: a proxy-less deployment (no trusted identity) and a SAR shape
    RBAC would answer `no` to for every viewer (exact, lowercase matching).

    NOTE ON PLACEMENT: `.github/workflows/ci.yml` points the `chart` job at THIS FILE.
    """

    def _docs(self, out):
        import yaml
        return [d for d in yaml.safe_load_all(out) if d]

    def _env(self, out, name):
        for d in self._docs(out):
            if d.get("kind") == "Deployment":
                for c in d["spec"]["template"]["spec"]["containers"]:
                    for e in c.get("env") or []:
                        if e["name"] == name:
                            return e["value"]
        return None

    def _configmap(self, out):
        import yaml
        for d in self._docs(out):
            if d.get("kind") == "ConfigMap" and d["metadata"]["name"].endswith("-config"):
                return yaml.safe_load(d["data"]["clusters.yaml"])
        raise AssertionError("no app ConfigMap in the rendered output")

    def test_restrictions_are_on_by_default_and_spelled_exactly(self):
        ok, out = render()
        assert ok, out
        assert self._env(out, "GSD_ENABLE_VIEW_RESTRICTIONS") == "true"
        # The requirements' typo must not propagate: a misspelt env var here is a
        # silently disabled security control.
        assert "RESCRICTIONS" not in out

    def test_disabling_is_expressible_and_explicit(self):
        ok, out = render(visibility__enabled="false")
        assert ok, out
        assert self._env(out, "GSD_ENABLE_VIEW_RESTRICTIONS") == "false"

    def test_a_nilled_block_keeps_restrictions_on(self):
        """Commenting out the stanza leaves `visibility:` present-but-nil; a bare field
        access panics and a naive `default` flips the control off. Neither may happen."""
        ok, out = render(visibility="null")
        assert ok, out
        assert self._env(out, "GSD_ENABLE_VIEW_RESTRICTIONS") == "true"
        cm = self._configmap(out)
        assert cm["visibilityAdminSarResource"] == "clusterrolebindings"
        assert cm["visibilityAdminSarVerb"] == "list"

    def test_the_sar_shape_reaches_the_configmap(self):
        ok, out = render(**{
            "visibility.adminSar.apiGroup": "rbac.authorization.k8s.io",
            "visibility.adminSar.resource": "rolebindings",
        })
        assert ok, out
        cm = self._configmap(out)
        assert cm["visibilityAdminSarApiGroup"] == "rbac.authorization.k8s.io"
        assert cm["visibilityAdminSarResource"] == "rolebindings"
        assert cm["visibilityAdminSarVerb"] == "list"

    def test_a_nonsensical_sar_shape_is_refused(self):
        """RBAC matching is exact and lowercase, so `List` would not error — it would
        answer no for every viewer and silently demote every administrator."""
        for key, bad in (("verb", "List"), ("resource", "Groups"),
                         ("apiGroup", "user.openshift.io/v1"), ("namespace", "Bad_NS")):
            ok, out = render(**{f"visibility.adminSar.{key}": bad})
            assert not ok, f"adminSar.{key}={bad!r} rendered happily"
            assert "visibility.adminSar" in out

    def test_visibility_without_the_proxy_is_refused(self):
        """No proxy means no trusted identity: X-Forwarded-User is whatever the caller
        typed, so the control cannot work and must not pretend to."""
        ok, out = render(oauthProxy__enabled="false")
        assert not ok, "a per-user control rendered with no authenticated identity"
        assert "requires oauthProxy.enabled=true" in out

    def test_declining_both_is_a_renderable_deliberate_choice(self):
        ok, out = render(oauthProxy__enabled="false", visibility__enabled="false")
        assert ok, out

    def test_the_sar_grant_is_present_on_a_default_install(self):
        """The tier check needs `create subjectaccessreviews`. It arrives via the stock
        system:auth-delegator binding, which used to render only for apiTokenAccess
        (off by default at the time) — so a default install would have failed every viewer
        closed to the self tier, permanently and invisibly."""
        ok, out = render()
        assert ok, out
        bindings = [d for d in self._docs(out)
                    if d.get("kind") == "ClusterRoleBinding"
                    and d["roleRef"]["name"] == "system:auth-delegator"]
        assert len(bindings) == 1, "the auth-delegator binding must render for the tier check"
        subject = bindings[0]["subjects"][0]
        assert subject["kind"] == "ServiceAccount"
        assert subject["name"] == "t-group-sync-dashboard"

    def test_the_sar_grant_disappears_when_nothing_needs_it(self):
        # apiTokenAccess is the other user of the grant, and on by default since chart 0.14.0.
        ok, out = render(visibility__enabled="false", oauthProxy__apiTokenAccess__enabled="false")
        assert ok, out
        assert not any(d.get("kind") == "ClusterRoleBinding"
                       and d["roleRef"]["name"] == "system:auth-delegator"
                       for d in self._docs(out)), (
            "with visibility off and apiTokenAccess off, nothing uses the SAR grant"
        )

    def test_notes_carry_the_grant_command_and_the_rollback_flag(self):
        notes = (CHART / "templates" / "NOTES.txt").read_text()
        assert "oc adm policy add-cluster-role-to-user cluster-reader" in notes
        assert "visibility.enabled=false" in notes

    # ── The tier cache lifetime ─────────────────────────────────────────────────────────

    def test_the_tier_ttl_threads_from_values_to_the_configmap(self):
        """The app has always read `visibilityTierTtlSeconds`, but for a while NOTHING rendered
        it — so the documented way to shorten the fail-open window after a revocation was an
        env override or a hand-edited ConfigMap. This is the values key that closes that."""
        ok, out = render()
        assert ok, out
        assert _config_data(out)["visibilityTierTtlSeconds"] == 60, "the shipped default"
        ok, out = render(visibility__tierTtlSeconds=15)
        assert ok, out
        assert _config_data(out)["visibilityTierTtlSeconds"] == 15

    def test_zero_is_a_legal_ttl_and_means_no_caching(self):
        """0 is not a malformed number — it disables caching, which an operator may genuinely
        want at the cost of a SubjectAccessReview per reader per request. Rejecting it would
        confuse "I chose immediate revocation" with "I typo'd"."""
        ok, out = render(visibility__tierTtlSeconds=0)
        assert ok, out
        assert _config_data(out)["visibilityTierTtlSeconds"] == 0

    def test_a_nilled_visibility_block_keeps_the_default_ttl(self):
        """Commenting the sub-keys out leaves `visibility:` present-but-nil, which a bare field
        access panics on — the same trap the adminSar helpers avoid."""
        ok, out = render(visibility="null")
        assert ok, out
        assert _config_data(out)["visibilityTierTtlSeconds"] == 60

    def test_a_fractional_or_negative_ttl_is_refused_at_render(self):
        """Both would reach the app's int() cast, fall back to 60, and leave the values file
        describing a cache that is not running — a quieter failure than a refused render. A
        negative would additionally make every entry instantly stale, turning the cache off
        while the file claims it is on."""
        for bad in ("1.5", "-5", "abc", "60s"):
            ok, out = render(visibility__tierTtlSeconds=bad)
            assert not ok, f"tierTtlSeconds={bad!r} rendered happily"
            assert "visibility.tierTtlSeconds" in out
            assert "whole number of seconds" in out

    # ── The Usage tab's second, stricter threshold (docs/SPEC_usage_admin_tier.md) ──────

    def test_the_usage_sar_default_is_a_write_verb_in_the_configmap(self):
        """Spec test 7: usageAdminSar threads into the ConfigMap, defaulting to the write verb
        that separates cluster-admin from cluster-reader (no read check does)."""
        ok, out = render()
        assert ok, out
        cm = self._configmap(out)
        assert cm["visibilityUsageAdminSarApiGroup"] == "rbac.authorization.k8s.io"
        assert cm["visibilityUsageAdminSarResource"] == "clusterrolebindings"
        assert cm["visibilityUsageAdminSarVerb"] == "update"
        assert cm["visibilityUsageAdminSarNamespace"] == ""

    def test_a_custom_usage_sar_shape_reaches_the_configmap(self):
        ok, out = render(**{
            "visibility.usageAdminSar.apiGroup": "",
            "visibility.usageAdminSar.resource": "secrets",
            "visibility.usageAdminSar.verb": "get",
        })
        assert ok, out
        cm = self._configmap(out)
        assert cm["visibilityUsageAdminSarApiGroup"] == ""      # the core group is expressible
        assert cm["visibilityUsageAdminSarResource"] == "secrets"
        assert cm["visibilityUsageAdminSarVerb"] == "get"

    def test_a_nilled_usage_block_keeps_the_default_write_check(self):
        """Commenting the sub-keys out leaves usageAdminSar present-but-nil; the nil-safe
        helpers must fall back to the default, never to an empty (allowed=false) check."""
        ok, out = render(**{"visibility.usageAdminSar": "null"})
        assert ok, out
        cm = self._configmap(out)
        assert cm["visibilityUsageAdminSarResource"] == "clusterrolebindings"
        assert cm["visibilityUsageAdminSarVerb"] == "update"

    def test_a_nonsensical_usage_sar_shape_is_refused(self):
        """Same exact-lowercase guard as adminSar: a miscased or versioned field would answer
        no for every viewer and silently demote every administrator, so it fails the render."""
        for key, bad in (("verb", "Update"), ("resource", "ClusterRoleBindings"),
                         ("apiGroup", "rbac.authorization.k8s.io/v1"), ("namespace", "Bad_NS")):
            ok, out = render(**{f"visibility.usageAdminSar.{key}": bad})
            assert not ok, f"usageAdminSar.{key}={bad!r} rendered happily"
            assert "visibility.usageAdminSar" in out

    def test_the_usage_tier_reuses_the_one_sar_grant(self):
        """The usage tier needs no new RBAC: it is the SAME `create subjectaccessreviews`
        (system:auth-delegator) the wide tier uses. So the default install carries exactly one
        such binding — one grant, two questions — and with visibility off the binding is still
        there, kept by its other consumer, API-token access (on by default since chart 0.14.0);
        the both-off state that removes it is `test_the_sar_grant_disappears_when_nothing_needs_it`."""
        def delegator_bindings(out):
            return [d for d in self._docs(out)
                    if d.get("kind") == "ClusterRoleBinding"
                    and d["roleRef"]["name"] == "system:auth-delegator"]
        ok, out = render()
        assert ok, out
        assert len(delegator_bindings(out)) == 1, "the usage tier must not add a second SAR grant"
        ok, out = render(visibility__enabled="false")
        assert ok, out
        assert len(delegator_bindings(out)) == 1, "token access alone keeps the one grant"


class TestProxyRequestLogging:
    """Off by default (review of chart 0.14.0, second pass): oauth-proxy's request logger writes the
    complete request URI, so the OAuth callback's `?code=…` would land in the pod log."""

    def test_off_by_default_and_explicitly_switchable(self):
        for value, expect in (("false", "-request-logging=false"), ("true", "-request-logging=true")):
            ok, out = render(oauthProxy__requestLogging=value) if value == "true" else render()
            assert ok, out
            assert expect in out and ("-request-logging=" + ("true" if value == "false" else "false")) not in out


class TestTheServiceMonitorVerifiesTLS:
    """The scrape must VERIFY the certificate, and the posture must be hard to lose.

    This block shipped as `insecureSkipVerify: true`, justified by a comment claiming
    verification was impossible: service-ca issues the certificate for the SERVICE DNS name
    while Prometheus dials the POD IP, so the name cannot match. The premise is true; the
    conclusion was not — `serverName` verifies against a name independent of the address
    dialled. Measured on the reference cluster before the fix: connecting to the pod IP while
    verifying against the service name returned HTTP 200 with ssl_verify_result=0, and the same
    call with no CA was refused, so that verification is real rather than a handshake that
    would have passed anyway.

    Nothing tested the posture, which is how it could be reverted green — and a revert would
    look like a simplification, because the wrong comment argued for it.
    """

    def _endpoint(self, out: str) -> dict:
        import yaml
        for doc in yaml.safe_load_all(out):
            if doc and doc.get("kind") == "ServiceMonitor":
                return doc["spec"]["endpoints"][0]
        raise AssertionError("no ServiceMonitor in the rendered output")

    def test_verification_is_on_and_anchored_on_the_service_name(self):
        ok, out = render(monitoring__serviceMonitor__enabled=True)
        assert ok, out
        ep = self._endpoint(out)
        assert ep["scheme"] == "https", (
            "the Service port targets the proxy container, which speaks TLS only — plain http "
            "fails the handshake on every scrape, silently"
        )
        tls = ep["tlsConfig"]
        assert not tls.get("insecureSkipVerify"), (
            "verification is achievable here; skipping it is a regression the old comment "
            "wrongly argued was unavoidable"
        )
        # The name must be the SERVICE, because the certificate carries no IP SAN.
        assert tls["serverName"].endswith(".svc")
        assert tls["ca"]["configMap"]["name"] == "openshift-service-ca.crt"
        assert tls["ca"]["configMap"]["key"] == "service-ca.crt"

    def test_the_verified_name_follows_the_release_and_namespace(self):
        """A hardcoded serverName would verify against the wrong name on any release whose
        fullname or namespace differs from the one it was written for — which fails closed
        (no metrics) rather than open, but fails silently either way."""
        ok, out = render(monitoring__serviceMonitor__enabled=True)
        assert ok, out
        import yaml
        name = next(d["metadata"]["name"] for d in yaml.safe_load_all(out)
                    if d and d.get("kind") == "ServiceMonitor")
        assert self._endpoint(out)["tlsConfig"]["serverName"].startswith(name + ".")

    def test_no_tls_block_at_all_when_the_proxy_is_off(self):
        """With no proxy the Service port targets the app, which speaks plain http — a scheme
        or tlsConfig here would fail every scrape on a deployment that never had TLS."""
        ok, out = render(monitoring__serviceMonitor__enabled=True,
                         oauthProxy__enabled=False, visibility__enabled=False)
        assert ok, out
        ep = self._endpoint(out)
        assert "scheme" not in ep and "tlsConfig" not in ep


class TestCurlInThePodTrustsWhatTheAppTrusts:
    """curl in the pod reads none of the application's settings — measured in the hardened image,
    it trusts the base's own bundle (/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem) and refuses
    a corporate-signed URL that the application, through GSD_TRUSTED_CA_FILE, verifies fine. The
    facts that decide the wiring, all measured:

    * curl consults a hashed directory only when told (`capath`), and a bundle file replaces its
      default bundle (`cacert`); every OpenSSL client already reads /etc/pki/tls/certs by default;
    * WITH CURL_CA_BUNDLE SET, CURL IGNORES SSL_CERT_DIR (curl 7.76 and 8.22: `-v` names only the
      CAfile). The first version of this chart set both and the hashed CA never reached curl
      while the injected bundle was on — the default. The tutorial's own verification found it;
    * curl's own configuration file names both, and only the curl tool reads it: `.curlrc` in the
      directory CURL_HOME names. `curl -v` then reports CAfile and CApath;
    * curl fails outright (exit 77) on an empty or missing `cacert`, and the injected ConfigMap is
      one 149-certificate file, so it can only ever be a `cacert`, never a hashed entry;
    * the manual ConfigMap carries one CA — the shape of a hashed entry (Hummingbird's
      "Approach 2"): mounted a second time as /etc/pki/tls/certs/<subject hash>.0 it reaches curl
      through `capath`, and urllib and the application's fallback context by default.

    Hence: a ConfigMap `<release>-curlrc` with `capath` always and `cacert` (the injected bundle)
    only when injected is on, mounted at /etc/curl, CURL_HOME=/etc/curl on the dashboard container
    and nothing on the proxy, no CURL_CA_BUNDLE and no SSL_CERT_DIR anywhere, and
    `trustedCA.existingConfigMap.subjectHash` adding the hashed mount.

    Placement: this file, for the reason given on TestTheProxyTrustsTheSameCAsTheApp.
    """

    INJECTED = "/etc/pki/ca-trust/extracted/pem/injected/ca-bundle.crt"
    HASHED_DIR = "/etc/pki/tls/certs"

    def _render(self, **values):
        import yaml
        ok, out = render(**values)
        assert ok, f"failed to render with {values}:\n{out}"
        docs = [d for d in yaml.safe_load_all(out) if d]
        dep = next(d for d in docs if d.get("kind") == "Deployment")
        spec = dep["spec"]["template"]["spec"]
        app = next(c for c in spec["containers"] if c["name"] == "dashboard")
        curlrc = next((d for d in docs if d.get("kind") == "ConfigMap" and d["metadata"]["name"].endswith("-curlrc")), None)
        return app, spec, curlrc, docs

    @staticmethod
    def _env(container):
        return {e["name"]: e.get("value") for e in container.get("env", [])}

    @staticmethod
    def _rc(curlrc) -> dict:
        """The .curlrc as {key: value}; one directive per line, `key = value`."""
        lines = [l for l in curlrc["data"][".curlrc"].splitlines() if l.strip()]
        return dict(l.split(" = ", 1) for l in lines)

    def test_no_environment_variable_carries_curls_trust(self):
        """The two variables cannot name both stores; the file can. Their absence is the fix."""
        for values in ({}, {"trustedCA__injected__enabled": "false"},
                       {"trustedCA__existingConfigMap__enabled": "true", "trustedCA__existingConfigMap__subjectHash": "c275f070"}):
            app, spec, _, _ = self._render(**values)
            for c in spec["containers"]:
                assert not {"CURL_CA_BUNDLE", "SSL_CERT_DIR", "SSL_CERT_FILE"} & set(self._env(c)), (values, c["name"])

    def test_default_curlrc_names_the_injected_bundle_and_the_hashed_directory(self):
        app, spec, curlrc, _ = self._render()
        assert curlrc, "no <release>-curlrc ConfigMap rendered"
        rc = self._rc(curlrc)
        assert rc == {"capath": self.HASHED_DIR, "cacert": self.INJECTED}, rc
        assert rc["cacert"] == self._env(app)["GSD_TRUSTED_CA_FILE"], "curl and the application read the same injected bundle"

    def test_without_the_injected_bundle_curlrc_names_only_the_directory(self):
        """The manual bundle must never become curl's `cacert`: it carries only the extra CA, and
        one `cacert` replaces the default bundle, dropping every public CA."""
        _, _, curlrc, _ = self._render(trustedCA__injected__enabled="false", trustedCA__existingConfigMap__enabled="true")
        assert self._rc(curlrc) == {"capath": self.HASHED_DIR}

    def test_curl_home_points_at_the_mounted_curlrc(self):
        app, spec, curlrc, _ = self._render()
        home = self._env(app)["CURL_HOME"]
        mount = next((m for m in app["volumeMounts"] if m["mountPath"] == home), None)
        assert mount and mount.get("readOnly") is True, f"nothing mounted at CURL_HOME={home}"
        volume = next(v for v in spec["volumes"] if v["name"] == mount["name"])
        assert volume["configMap"]["name"] == curlrc["metadata"]["name"], "the mount must be the curlrc ConfigMap, not another"
        assert "subPath" not in mount, "curl reads $CURL_HOME/.curlrc: the ConfigMap is mounted as the directory"

    def test_the_injected_bundle_curl_is_given_is_mounted_and_optional(self):
        app, spec, curlrc, _ = self._render()
        path = self._rc(curlrc)["cacert"]
        parent, name = path.rsplit("/", 1)
        assert name == "ca-bundle.crt", "the key OpenShift writes into the injected ConfigMap"
        mount = next((m for m in app["volumeMounts"] if m["mountPath"] == parent), None)
        assert mount, f"nothing mounted at {parent}"
        volume = next(v for v in spec["volumes"] if v["name"] == mount["name"])
        assert volume["configMap"]["name"].endswith("-trusted-ca")
        assert volume["configMap"].get("optional") is True, (
            "the injected ConfigMap is populated after creation; a required volume would block "
            "the first rollout of every install"
        )

    def test_the_injected_configmap_carries_the_injection_label(self):
        _, _, _, docs = self._render()
        cms = [d for d in docs if d.get("kind") == "ConfigMap" and d["metadata"]["name"].endswith("-trusted-ca")]
        assert len(cms) == 1
        assert cms[0]["metadata"]["labels"]["config.openshift.io/inject-trusted-cabundle"] == "true"

    def test_the_proxy_container_is_left_alone(self):
        """oauth-proxy is Go; it takes its CAs as -openshift-ca and reads no curl or OpenSSL variable."""
        _, spec, _, _ = self._render()
        proxy = next(c for c in spec["containers"] if c["name"] == "oauth-proxy")
        assert "CURL_HOME" not in self._env(proxy)
        assert not any(m["mountPath"] == "/etc/curl" for m in proxy.get("volumeMounts", []))

    def test_a_subject_hash_mounts_the_manual_ca_into_the_hashed_directory(self):
        app, spec, curlrc, _ = self._render(
            trustedCA__existingConfigMap__enabled="true",
            trustedCA__existingConfigMap__subjectHash="c275f070",
        )
        hashed = next((m for m in app["volumeMounts"] if m["mountPath"] == f"{self.HASHED_DIR}/c275f070.0"), None)
        assert hashed, f"no hashed mount among {[m['mountPath'] for m in app['volumeMounts']]}"
        assert hashed["subPath"] == "ca-bundle.crt", "subPath must name the ConfigMap key"
        assert hashed.get("readOnly") is True
        enterprise = next(m for m in app["volumeMounts"] if m["mountPath"].endswith("/enterprise"))
        assert hashed["name"] == enterprise["name"], "the same ConfigMap volume, not a second copy"
        assert not any(m["mountPath"].rstrip("/") == self.HASHED_DIR for m in app["volumeMounts"]), (
            "the whole directory must never be mounted over: it would hide the base's hashed links"
        )
        assert self._rc(curlrc)["capath"] == self.HASHED_DIR, "and curl is told to read that directory"

    def test_no_subject_hash_means_no_hashed_mount(self):
        app, _, _, _ = self._render(trustedCA__existingConfigMap__enabled="true")
        assert not any(self.HASHED_DIR in m["mountPath"] for m in app["volumeMounts"])

    def test_a_subject_hash_without_the_configmap_is_refused(self):
        """A hash with nothing to mount is a values typo, not a no-op."""
        ok, out = render(trustedCA__existingConfigMap__subjectHash="c275f070")
        assert not ok
        assert "subjectHash is set but trustedCA.existingConfigMap.enabled is false" in out, out

    @pytest.mark.parametrize("bad", ["not-a-hash", "C275F070", "c275f07", "c275f0701", "c275f070.", "c275f070.x"])
    def test_a_malformed_subject_hash_is_refused(self, bad):
        """OpenSSL looks up exactly eight lowercase hex digits, plus a numeric collision suffix;
        anything else is a file the lookup never consults, silently."""
        ok, out = render(
            trustedCA__existingConfigMap__enabled="true",
            trustedCA__existingConfigMap__subjectHash=bad,
        )
        assert not ok
        assert "is not an OpenSSL subject hash" in out, out

    def test_a_collision_suffix_is_honoured_verbatim(self):
        """`.1` is OpenSSL's own answer to two CAs with one subject hash; the base's `.0` must not
        be shadowed to add ours."""
        app, _, _, _ = self._render(
            trustedCA__existingConfigMap__enabled="true",
            trustedCA__existingConfigMap__subjectHash="c275f070.1",
        )
        assert any(m["mountPath"] == f"{self.HASHED_DIR}/c275f070.1" for m in app["volumeMounts"])
        assert not any(m["mountPath"] == f"{self.HASHED_DIR}/c275f070.1.0" for m in app["volumeMounts"])


class TestGroupCountCliffValues:
    def test_configmap_carries_the_keys_and_joins_the_silence_list(self):
        ok, out = render(**{
            "config__alerts__groupCountCliff__minMembers": 25,
            "config__alerts__groupCountCliff__silence[0]": "app-ocp-rbac-a-*",
            "config__alerts__groupCountCliff__silence[1]": "app-ocp-rbac-b-ns-view",
        })
        assert ok, out
        cfg = _config_data(out)
        assert cfg["groupCountCliffEnabled"] is True
        assert (cfg["groupCountCliffMinMembers"], cfg["groupCountCliffDropRatio"],
                cfg["groupCountCliffWindowHours"]) == (25, 0.5, 24)
        assert cfg["groupCountCliffSilence"] == "app-ocp-rbac-a-*,app-ocp-rbac-b-ns-view"

    def test_the_rule_summary_names_the_configured_ratio_not_the_word_half(self):
        ok, out = render(**{"monitoring__prometheusRule__enabled": "true",
                            "config__alerts__groupCountCliff__dropRatio": "0.3"})
        assert ok, out
        assert "lost at least 30% of their members" in out
        assert "half their members" not in out
        ok, out = render(**{"monitoring__prometheusRule__enabled": "true"})
        assert ok and "lost at least 50% of their members" in out

    def test_a_window_shorter_than_the_poll_interval_refuses_the_render(self):
        ok, out = render(**{"config__pollIntervalSeconds": "3600",
                            "config__alerts__groupCountCliff__windowHours": "0.5"})
        assert not ok and "must cover at least one poll interval" in out
        ok, out = render(**{"config__pollIntervalSeconds": "3600",
                            "config__alerts__groupCountCliff__windowHours": "1"})
        assert ok, out

    @pytest.mark.parametrize("key,value", [
        ("config__alerts__groupCountCliff__dropRatio", "0"),
        ("config__alerts__groupCountCliff__dropRatio", "1.5"),
        ("config__alerts__groupCountCliff__minMembers", "0"),
        ("config__alerts__groupCountCliff__windowHours", "0"),
    ])
    def test_a_threshold_that_cannot_or_always_fires_refuses_the_render(self, key, value):
        ok, out = render(**{key: value})
        assert not ok
        assert "config.alerts.groupCountCliff" in out


class TestUiExportModule:
    """The export switch threads from values to the ConfigMap key the app reads, in both states.

    Lives here because ci.yml's `chart` job runs this file by name.
    """

    def test_on_by_default(self):
        ok, out = render()
        assert ok, out
        assert _config_data(out)["uiExportEnabled"] is True

    def test_off_reaches_the_app_as_false(self):
        ok, out = render(ui__export__enabled="false")
        assert ok, out
        assert _config_data(out)["uiExportEnabled"] is False


class TestTheIdentitiesGrantIsOffReadOnlyAndCoupled:
    """C2: rbac.identities is both the grant and the read switch; off by default (a grant), get/list
    only, refused without rbac.users, and the allow-list threads to the ConfigMap as a comma list."""

    def _docs(self, out):
        import yaml
        return [d for d in yaml.safe_load_all(out) if d]

    def _rules(self, out):
        return [r for d in self._docs(out) if d.get("kind") == "ClusterRole" for r in d.get("rules") or []]

    def test_default_renders_no_identities_rule_and_the_read_off(self):
        ok, out = render()
        assert ok, out
        assert not [r for r in self._rules(out) if "identities" in (r.get("resources") or [])]
        assert _config_data(out)["identitiesReadEnabled"] is False
        assert _config_data(out)["usersProviders"] == []

    def test_on_renders_exactly_get_and_list(self):
        ok, out = render(rbac__identities="true")
        assert ok, out
        rules = [r for r in self._rules(out) if "identities" in (r.get("resources") or [])]
        assert len(rules) == 1 and sorted(rules[0]["verbs"]) == ["get", "list"]
        assert rules[0]["apiGroups"] == ["user.openshift.io"]
        assert _config_data(out)["identitiesReadEnabled"] is True

    def test_identities_without_users_is_refused_naming_the_pair(self):
        ok, out = render(rbac__identities="true", rbac__users="false")
        assert not ok and "rbac.identities=true requires rbac.users=true" in out

    def test_the_allow_list_reaches_the_configmap_as_a_list_without_losing_legal_names(self):
        """Review (Codex): OpenShift accepts a provider named `a,b` or `a b`; a comma join would
        split the first. The key is a YAML flow sequence the app reads as a list."""
        # `--set` splits on a bare comma, so the comma is escaped for helm's parser; the chart
        # receives the literal `a,b`.
        ok, out = render(**{"config__users__providers[0]": r"a\,b", "config__users__providers[1]": "a b",
                            "config__users__providers[2]": "ldap-local"})
        assert ok, out
        assert _config_data(out)["usersProviders"] == ["a,b", "a b", "ldap-local"]
