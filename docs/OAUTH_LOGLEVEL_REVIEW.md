# OAuth log-level Job — review, findings and remediation

Status: **open — Reviewer A + Reviewer B merged; arbiter findings added; awaiting Codex, then
arbitration.**

Feature under review: the two Helm hook Jobs that set `authentications.operator.openshift.io/cluster`
`spec.logLevel` to `Debug` and back. This is the PREREQUISITE for a later login-capture feature and
nothing more.

Scope is exactly seven files — the three new templates, the `oauthDebug` values block, the two docs,
and the new test class in `test_chart_strategy.py`. Everything else in the repo is out of scope.

Two Fable reviewers ran independently at `xhigh` reasoning. Finding ids are prefixed `A` and `B` by
reviewer; `C` sections below are the arbiter's own, found while deploying and testing on the live
cluster. **24 reviewer findings + 3 arbiter findings.** Nothing here is applied yet.

## Where the reviewers agree

Two findings were reached independently by both, which raises confidence and makes them the first to
fix:

| both found | A | B |
|---|---|---|
| the wait loop's `get deployments` grant is cluster-wide for a loop that reads ONE Deployment | A7 | B3 |
| `waitSeconds >= activeDeadlineSeconds` renders unchecked and breaks the "a timeout is not a failure" promise | A6 | B2 |

And the single most important finding of the whole review is B1, because it undermines the reason the
feature is shaped the way it is: **the invariant is only half-guarded.** The write ClusterRole is
tested, but its *binding subject* is not — rebinding the write role to the dashboard's ServiceAccount
passes all 30 tests, while the chart README claims the suite would fail. The separation the design
exists to enforce is not actually enforced.

---

## Verdict

Not shippable as it stands, for one reason above all others: the wait loop in
`oauth-debug-job.yaml` reproduces, byte for byte, the failure its own comment says it was written
to prevent. It checks steady-state conditions (`obs == gen`, all replicas available and updated)
that are equally true in the ~30-second window **before** the operator reconciles the patch, so it
breaks on its first poll and prints "rollout complete" while the oauth pods still serve the old
level — and I caught it doing exactly that on the live cluster: the Job's own log says
`rollout complete: generation 26` at 07:27:47Z, and the generation-27 pod did not start until
07:28:16Z, 29 seconds later. The fix is a three-line baseline capture (F1). Two more silent-failure
paths (a rollback that never re-applies the level, F2; a failed `oc get` masquerading as "already
Normal", F3) round out the correctness set. Everything else is bounded tech debt with one-comment
or one-line fixes. The security posture of the pod specs, the RBAC pin on the write, the hook
lifecycle ordering and the two-switch convergence design are sound, and several of them I could
verify against the real cluster rather than by reading.

## Findings and remediation

### A1. The wait loop declares "rollout complete" before the rollout begins

- **Severity**: high
- **Category**: correctness
- **Location**: `charts/group-sync-dashboard/templates/oauth-debug-job.yaml:77-119`
- **Claim**: The break condition — `[ "$obs" = "$gen" ] && avail>=want && upd>=want` — is a
  steady-state invariant that is also true for the entire window between `oc patch` landing and
  the cluster-authentication-operator reconciling the Deployment (~30s, per the measured
  `oc rollout status` fact this very loop was written to replace). With no baseline taken before
  the patch, the first poll iteration sees the OLD generation fully rolled out and breaks
  immediately, printing "rollout complete" while the oauth pods still serve the old log level.
- **Trigger**: any run where `CURRENT != WANT` (i.e. any run that actually patches). The loop is
  only ever reached after a patch, so the trigger is the feature's primary code path.
- **Evidence**: three independent pieces, all from the live cluster today.

  1. The exact break condition, evaluated read-only against the current pre-patch steady state,
     breaks instantly:

     ```
     $ gen=...; obs=...; want=...; avail=...; upd=...   # the Job's five oc get calls, verbatim
     gen=27 obs=27 want=1 avail=1 upd=1
     LOOP WOULD BREAK: rollout complete: generation 27, 1/1 available and updated
     ```

  2. A real run of this Job finished on the cluster minutes before this review. Its log
     (`oc logs -n group-sync-dashboard group-sync-dashboard-oauth-loglevel-6fkmx`):

     ```
     requested logLevel: Normal
     current logLevel:   Debug
     patching authentications.operator.openshift.io/cluster -> Normal
     authentication.operator.openshift.io/cluster patched
     waiting up to 180s for the oauth-openshift rollout
     rollout complete: generation 26, 1/1 available and updated
     ✅ OAuth server logLevel is now Normal
     ```

     It declared completion at generation **26**. The deployment is now at generation **27** —
     the rollout its patch caused happened after it exited.

  3. The timeline. The Job container terminated at `2026-08-07T07:27:47Z`
     (`.status.containerStatuses[0].state.terminated.finishedAt`); the current oauth pod —
     ReplicaSet revision 27, the post-patch one — started at `2026-08-07T07:28:16Z`
     (`oc get pods -n openshift-authentication -l app=oauth-openshift`):

     ```
     NAME                               STARTED
     oauth-openshift-7d4d7cc74c-jvx44   2026-08-07T07:28:16Z
     ```

     The Job exited claiming the rollout was complete **29 seconds before the new pod started** —
     the same ~30s operator-reconcile window the in-file comment documents for `oc rollout status`.
- **Cost if unfixed**: the downstream login-capture feature starts reading logs the moment this
  Job reports success, finds pods still at the old level, and "looks broken" — the precise outcome
  the loop's own comment promises to prevent. Whoever debugs it will read the Job log, see
  "rollout complete", and look everywhere except here. The `enabled=false` direction is worse:
  the Job prints "logLevel is now Normal" while Debug lines — usernames, LDAP DNs — keep being
  written for another half minute or more.
- **REMEDIATION**: capture the Deployment's generation BEFORE the patch and require it to have
  moved. Replace lines 77–119 (from `echo "patching ..."` through `done`) with:

  ```bash
          # Baseline BEFORE the patch. The operator takes tens of seconds to react (measured:
          # ~30s on the reference cluster), and until it does the Deployment sits at its OLD
          # generation with observedGeneration caught up and every replica available — a state
          # indistinguishable from "rollout finished" except by knowing the generation we
          # started from. Without this the loop breaks on its first poll.
          PRE_GEN=$(oc get deploy oauth-openshift -n openshift-authentication \
                      -o jsonpath='{.metadata.generation}' 2>/dev/null || echo 0)

          echo "patching authentications.operator.openshift.io/cluster -> ${WANT}"
          oc patch authentications.operator.openshift.io cluster --type=merge \
            -p "{\"spec\":{\"logLevel\":\"${WANT}\"}}"

          # DO NOT TRUST `oc rollout status` HERE, and this is measured rather than cautious: on the
          # reference cluster it returned "successfully rolled out" roughly THIRTY SECONDS BEFORE the
          # rollout began, because at that moment the old ReplicaSet was still the current one and
          # complete. A Job that patched and then trusted it would report success while the oauth
          # pods were still serving the old level, and the capture that depends on this would find
          # nothing and look broken.
          #
          # The operator reconciles the Deployment itself, so what we wait on is the DEPLOYMENT's
          # generation moving past the pre-patch baseline, its observedGeneration catching up, and
          # its replicas becoming available — not our patch being accepted, which says nothing
          # about the pods.
          DEADLINE=$(( $(date +%s) + {{ .Values.oauthDebug.waitSeconds }} ))
          echo "waiting up to {{ .Values.oauthDebug.waitSeconds }}s for the oauth-openshift rollout (generation was ${PRE_GEN})"
          while :; do
            if [ "$(date +%s)" -ge "$DEADLINE" ]; then
              echo "⚠️  timed out waiting for the rollout. The level IS set — confirm the pods with:"
              echo "    oc get pods -n openshift-authentication"
              echo "    oc logs deploy/oauth-openshift -n openshift-authentication | grep 'for login'"
              # NOT a failure. The patch landed, which is this Job's actual job; the rollout is the
              # operator's to finish, and failing here would fail `helm upgrade` over somebody
              # else's slow reconcile.
              exit 0
            fi
            gen=$(oc get deploy oauth-openshift -n openshift-authentication \
                    -o jsonpath='{.metadata.generation}' 2>/dev/null || echo 0)
            obs=$(oc get deploy oauth-openshift -n openshift-authentication \
                    -o jsonpath='{.status.observedGeneration}' 2>/dev/null || echo -1)
            want=$(oc get deploy oauth-openshift -n openshift-authentication \
                    -o jsonpath='{.spec.replicas}' 2>/dev/null || echo 1)
            avail=$(oc get deploy oauth-openshift -n openshift-authentication \
                    -o jsonpath='{.status.availableReplicas}' 2>/dev/null || echo 0)
            upd=$(oc get deploy oauth-openshift -n openshift-authentication \
                    -o jsonpath='{.status.updatedReplicas}' 2>/dev/null || echo 0)
            # The generation must have MOVED past the baseline before the steady-state checks mean
            # anything — they are all true in the pre-reconcile window too. A failed baseline read
            # (PRE_GEN=0) degrades to the old check rather than wedging the loop.
            if [ "${gen:-0}" -gt "${PRE_GEN:-0}" ] && [ "$obs" = "$gen" ] \
               && [ "${avail:-0}" -ge "${want:-1}" ] && [ "${upd:-0}" -ge "${want:-1}" ]; then
              echo "rollout complete: generation ${PRE_GEN} -> ${gen}, ${avail}/${want} available and updated"
              break
            fi
            sleep 5
          done
  ```

  Note the degradations are all benign by design: if the baseline read fails, `PRE_GEN=0` and any
  real generation passes (the old behaviour); if the operator's reconcile turns out to be a no-op
  for the Deployment, the loop reaches the timeout path, which already exits 0 with an accurate
  message ("The level IS set").
- **Test that would catch a regression** (in `TestTheOauthLogLevelJobKeepsTheWriteOffTheDashboard`,
  or a sibling class — the class already carries `ON` and `_docs`):

  ```python
      def test_the_wait_loop_baselines_the_generation_before_patching(self):
          """The pre-reconcile steady state — obs==gen, every replica available — is
          indistinguishable from 'rollout finished' without knowing the generation the patch
          started from. Measured live: the Job printed 'rollout complete: generation 26' at
          07:27:47Z and the generation-27 pod started at 07:28:16Z, 29 seconds later."""
          ok, out = render(**self.ON, oauthDebug__enabled="true")
          assert ok, out
          script = out[out.index("name: set-loglevel"):]
          if "name: revert-loglevel" in script:
              script = script[:script.index("name: revert-loglevel")]
          assert "PRE_GEN=" in script, "the pre-patch generation baseline is gone"
          assert script.index("PRE_GEN=") < script.index("oc patch"), (
              "the baseline must be read BEFORE the patch, or it baselines the new generation"
          )
          assert '"${gen:-0}" -gt "${PRE_GEN:-0}"' in script, (
              "the break condition no longer requires the generation to move past the baseline"
          )
  ```
- **Risk of the remediation**: two edges, both already covered by existing paths. (1) Baseline
  read fails → `PRE_GEN=0` → behaves exactly as today, no worse. (2) The operator never bumps the
  Deployment generation (semantic no-op) → the loop runs to `waitSeconds` and exits 0 through the
  timeout branch, whose message is accurate. Verify by re-running the exact five-`oc get`
  condition snippet above pre-patch: with the fix it must print "loop would continue" against a
  steady-state cluster, and the Job's next real run must log a `generation N -> N+1` transition.

> **Codex:** **FIX-INADEQUATE** — the defect is confirmed, but `PRE_GEN` is correlation, not
> causation. I ran the proposed predicate over synthetic snapshots: an unrelated steady rollout
> (`PRE_GEN=26, gen=obs=27, want=avail=upd=1`) returns true, while a legitimate reconcile that does
> not change the Deployment generation returns false and consumes the whole wait. The CR fields are
> not a complete substitute: OpenShift defines `status.observedGeneration` only as the last CR
> generation the operator has “dealt with,” and `status.generations[].lastGeneration` as workload
> bookkeeping, not proof that the requested log level is live
> ([operator API](https://docs.redhat.com/en/documentation/openshift_container_platform/4.21/html/operator_apis/authentication-operator-openshift-io-v1#operator-apis-authentication-operator-openshift-io-v1)).
> The stronger signal is already in the operand: upstream renders `oauth-server ... --v=${LOG_LEVEL}`
> ([deployment manifest](https://github.com/openshift/cluster-authentication-operator/blob/master/bindata/oauth-openshift/deployment.yaml#L51-L56)),
> and the installed OpenShift API types describe Normal/Debug as verbosity 2/4. Wait for the
> Deployment template's `LOG_LEVEL` environment value to match `WANT`, then apply Kubernetes' full
> completion predicate. `status.observedGeneration >=` the post-patch CR generation is a useful
> causal gate, but is not rollout completion. The live `oc get` requested for this pass could not
> run: sandbox policy rejected the configured `127.0.0.1:6443` connection before authentication; no
> cluster state was touched.

### A2. `helm rollback` never runs the Job, so a rollback silently strands the level

- **Severity**: medium
- **Category**: correctness
- **Location**: `charts/group-sync-dashboard/templates/oauth-debug-job.yaml:36`
- **Claim**: The hook list is `post-install,post-upgrade`, but Helm executes only `pre-rollback`
  and `post-rollback` hooks on `helm rollback` (Helm 3 hook catalogue; v3.14.0 in use here). The
  chart's whole two-switch argument — "Helm does not run a Job you merely stopped rendering" —
  has a third door it does not cover: a rollback from `enabled=true` to an `enabled=false`
  revision restores the values but never re-applies the level, leaving the cluster in Debug while
  the release says Normal.
- **Trigger**: `helm upgrade --set oauthDebug.manage=true,oauthDebug.enabled=true`, then
  `helm rollback <release>` to the prior revision (`enabled=false` or pre-feature). Also the
  brief's "upgrade that fails AFTER the Job ran" case: the standard recovery for a failed upgrade
  is a rollback, which then skips the Job.
- **Evidence**: the rendered annotation, from
  `helm template t charts/group-sync-dashboard --set ingress.host=t.example.com --set oauthDebug.manage=true`:

  ```
    annotations:
      helm.sh/hook: post-install,post-upgrade
  ```

  No `post-rollback`. Helm's documented hook set for rollback is `pre-rollback`/`post-rollback`
  only, and rollback re-renders the TARGET revision's manifests — so a Job present in that
  revision but annotated only for install/upgrade is rendered and then never executed.
- **Cost if unfixed**: the person who rolls back believes the cluster matches the restored values
  — every surface (values, manifests, README) says Normal — while the OAuth server keeps naming
  every login. Nothing will ever correct it until the next `helm upgrade`, which may be weeks
  away. It is the exact "strand the cluster in Debug" failure the two-switch design exists to
  prevent, through a different door.
- **REMEDIATION**: replace the annotations block (lines 35–40) with:

  ```yaml
    annotations:
      # post-rollback too: `helm rollback` runs ONLY pre/post-rollback hooks and re-renders the
      # TARGET revision's manifests. Without it, rolling back from enabled=true restores the
      # values but never re-applies the level — the same one-way strand the two-switch design
      # exists to prevent, through a different door. The script applies the REQUESTED level, so
      # running it on rollback converges to whatever the rolled-back-to revision asked for.
      helm.sh/hook: post-install,post-upgrade,post-rollback
      # before-hook-creation, so an upgrade replaces the previous run rather than failing on a name
      # that already exists. NOT hook-succeeded: the log of what this changed on the cluster is worth
      # keeping until the next upgrade.
      helm.sh/hook-delete-policy: before-hook-creation
  ```
- **Test that would catch a regression**:

  ```python
      def test_the_job_also_runs_on_rollback(self):
          """`helm rollback` executes ONLY pre/post-rollback hooks. Without post-rollback, a
          rollback from enabled=true to an enabled=false revision restores the values but leaves
          the cluster in Debug — a silent one-way strand."""
          ok, out = render(**self.ON)
          assert ok, out
          jobs = [d for d in self._docs(out) if d.get("kind") == "Job"
                  and not d["metadata"]["name"].endswith("-revert")]
          assert len(jobs) == 1, "expected exactly one apply Job"
          hooks = jobs[0]["metadata"]["annotations"]["helm.sh/hook"].split(",")
          assert "post-rollback" in hooks, (
              "a rollback must re-apply the rolled-back-to revision's requested level"
          )
  ```
- **Risk of the remediation**: a rollback now runs a Job it previously did not. The script is
  idempotent (the `CURRENT == WANT` shortcut exits 0 without patching), `before-hook-creation`
  replaces any prior run's Job object, and a rollback to a pre-feature revision renders no Job at
  all, so nothing runs — unchanged. Residual known gap, inherent and documented: rolling back to
  a `manage=false` revision runs nothing, which matches `manage=false`'s "never touches" contract.
  Verify with `helm template` on both an `enabled=true` and `enabled=false` values set: the only
  diff in the Job should be the annotation and `WANT=`.

> **Codex:** **FIX-INADEQUATE** — Helm 3.14.0 locally exposes rollback hooks, and Helm documents
> `post-rollback`, so the added annotation is correct for a target revision that already contains it.
> But Helm executes hooks from the *target* release, not the revision being left
> ([Helm's target-hook explanation](https://github.com/helm/helm/issues/5825#issuecomment-569738746)).
> Therefore the first rollback to an enabled-false revision created before this fix, a pre-feature
> revision, or a `manage=false` revision still has no runnable revert hook. That is part of A2's own
> trigger but is not cured by the proposed code. Keep `post-rollback`, and add explicit manual-revert
> guidance plus the migration rule “establish one fixed, `manage=true,enabled=false` revision before
> enabling Debug.” Also update B6's exact hook assertion; as written it rejects this fix.

### A3. A failed `oc get` masquerades as "already Normal" in both Jobs

- **Severity**: medium
- **Category**: correctness
- **Location**: `charts/group-sync-dashboard/templates/oauth-debug-job.yaml:67-75` and
  `charts/group-sync-dashboard/templates/oauth-debug-revert-job.yaml:49-56`
- **Claim**: `CURRENT=$(oc get ... 2>/dev/null || true)` maps every failure — 403, API timeout,
  DNS blip — to the empty string, and `${CURRENT:-Normal}` then maps empty to `Normal`. The
  scripts cannot distinguish "the field is unset" (genuinely means Normal) from "the API said no"
  (means nothing), and on the failure path they print "already Normal — nothing to do/revert" and
  exit 0. The revert Job's own header says "Every failure below is reported and then forgiven" —
  this failure is neither reported (stderr is discarded) nor forgiven (it is misreported as
  success).
- **Trigger**: any transient API failure during the read. For the revert Job: during
  `helm uninstall` with the cluster in Debug — the uninstall completes, the RBAC is deleted, and
  Debug stays on with nothing left that can revert it. For the main Job: `enabled=false` upgrade
  with a read blip — upgrade reports success, cluster stays Debug.
- **Evidence**: the script's exact logic with a failing `oc`, both shell modes:

  ```
  $ bash -c 'set -uo pipefail
    oc() { echo "Error from server (Forbidden): ..." >&2; return 1; }
    CURRENT=$(oc get authentications.operator.openshift.io cluster \
                -o jsonpath="{.spec.logLevel}" 2>/dev/null || true)
    echo "current logLevel: ${CURRENT:-<unset, i.e. Normal>}"
    if [ "${CURRENT:-Normal}" = "Normal" ]; then
      echo "already Normal — nothing to revert"; exit 0; fi'
  current logLevel: <unset, i.e. Normal>
  already Normal — nothing to revert
  ```

  Identical result under the main Job's `set -euo pipefail` with `WANT=Normal`
  (`already Normal — nothing to do`, exit 0). The Forbidden error is invisible: `2>/dev/null`.
- **Cost if unfixed**: the worst version is the uninstall path — it is the one shot at reverting,
  it self-reports success, and afterwards the SA/ClusterRole that could have fixed it are gone.
  Debug then names every login, with LDAP DNs, indefinitely, and the Job log actively misleads
  the person who eventually investigates ("already Normal").
- **REMEDIATION**: only shortcut when the read *succeeded*; on failure, fall through to the
  idempotent merge-patch (whose own failure path already reports correctly). Drop `2>/dev/null`
  so the real error lands in the log.

  Main Job — replace lines 67–75 with:

  ```bash
          # No `|| true` and no 2>/dev/null on the read: a FAILED read is not an UNSET field.
          # ${CURRENT:-Normal} maps empty to Normal — right for "the field is absent", wrong for
          # "the API said no", where it would print "already Normal — nothing to do" and exit 0
          # with the cluster still in Debug. On a failed read, patch unconditionally: merge-
          # patching the level we want is idempotent.
          if CURRENT=$(oc get authentications.operator.openshift.io cluster \
                         -o jsonpath='{.spec.logLevel}'); then
            # An unset logLevel means the operator default, which IS Normal — so treat the two as
            # the same rather than patching a cluster that is already where we want it.
            echo "current logLevel:   ${CURRENT:-<unset, i.e. Normal>}"
            if [ "${CURRENT:-Normal}" = "$WANT" ]; then
              echo "already ${WANT} — nothing to do"
              exit 0
            fi
          else
            echo "could not read the current level — applying ${WANT} unconditionally"
          fi
  ```

  Revert Job — replace lines 49–56 with:

  ```bash
          # No `|| true` on the read: a FAILED read is not "unset". ${CURRENT:-Normal} maps
          # empty to Normal, so an API blip here would print "already Normal — nothing to
          # revert" and skip the one thing this Job exists to do. On a failed read, fall
          # through to the patch — merge-patching Normal is idempotent, and if the API is truly
          # unreachable the patch's own failure path below prints the manual fix.
          if CURRENT=$(oc get authentications.operator.openshift.io cluster \
                         -o jsonpath='{.spec.logLevel}'); then
            echo "current logLevel: ${CURRENT:-<unset, i.e. Normal>}"
            if [ "${CURRENT:-Normal}" = "Normal" ]; then
              echo "already Normal — nothing to revert"
              exit 0
            fi
          else
            echo "could not read the current level — attempting the revert anyway"
          fi
  ```

  (`if CURRENT=$(...)` does not trip `set -e`: a command tested by `if` is exempt from errexit.
  In the main Job, a read failure followed by a patch failure still fails the pod — the correct
  signal, retried by `backoffLimit`.)
- **Test that would catch a regression**:

  ```python
      def test_a_failed_read_never_masquerades_as_already_done(self):
          """`CURRENT=$(oc get ... || true)` maps an API failure to the empty string, and
          ${CURRENT:-Normal} maps empty to Normal: a 403 or timeout becomes 'already Normal',
          exit 0, cluster still in Debug. Both Jobs must fall through to the idempotent patch
          instead of inventing that answer — verified by simulating a failing oc through the
          script's exact logic."""
          ok, out = render(**self.ON)
          assert ok, out
          assert out.count("could not read the current level") == 2, (
              "both Jobs must distinguish a FAILED read from an UNSET field"
          )
  ```
- **Risk of the remediation**: on a genuinely broken API, the main Job now attempts a patch that
  fails and (via `set -e`) fails the pod — but that path failed the pod before too, one command
  later; no new failure mode. The revert Job on a broken API attempts the patch, hits its
  existing `else` branch, prints the manual fix and exits 0 — strictly better reporting, same
  exit code. Verify by re-running the two simulation snippets above against the fixed scripts:
  the failure path must print "could not read" and reach the patch.

> **Codex:** **CONFIRMED** — I executed the current shell with an `oc()` stub returning Forbidden:
> stderr disappeared, `CURRENT` became empty, and the branch printed `already Normal`; the proposed
> `if CURRENT=$(oc get ...)` version preserved stderr and reached the patch path. What the earlier
> pass missed is test strength: `out.count("could not read the current level") == 2` only proves two
> strings render, not that either failed read reaches `oc patch`. Keep the code fix, but make the test
> execute the extracted scripts with a failing `oc` stub (or at minimum assert the `if CURRENT=`
> control-flow and the patch occur in the same parsed Job command).

### A4. A pod-level failure of the pre-delete hook blocks uninstall, and the "every OpenShift cluster" image claim has a documented exception

- **Severity**: medium
- **Category**: tech-debt
- **Location**: `charts/group-sync-dashboard/templates/oauth-debug-revert-job.yaml:44-46`,
  `charts/group-sync-dashboard/values.yaml:595-605`, `charts/group-sync-dashboard/README.md:213`
- **Claim**: The revert Job's comment promises "an operator trying to remove this chart must
  never be held hostage by a best-effort tidy-up", but `set -uo pipefail` + `exit 0` only forgives
  *script* failures. A pod that never starts — image unreachable, unschedulable — fails the Job at
  `activeDeadlineSeconds`, and Helm aborts an uninstall whose pre-delete hook fails: the release
  stays. The likeliest cause is the image default itself: the `openshift/cli` *imagestream* ships
  everywhere, but the internal registry that serves
  `image-registry.openshift-image-registry.svc:5000` is bootstrapped as `Removed` on platforms
  without shareable object storage (bare metal, agnostic/none-platform installs — OpenShift
  Image Registry Operator documented behaviour), so on those clusters every hook in this feature
  is ErrImagePull and both install and uninstall wedge. Neither the `--no-hooks` escape hatch nor
  the registry caveat is written down anywhere.
- **Trigger**: `helm uninstall` (or install/upgrade with `manage=true`) on a cluster where
  `oc get configs.imageregistry.operator.openshift.io cluster -o jsonpath='{.spec.managementState}'`
  returns `Removed`, or any cluster-local event that makes the image unpullable during an
  uninstall.
- **Evidence**: the reference cluster happens to be the good case —

  ```
  $ oc get configs.imageregistry.operator.openshift.io cluster -o jsonpath='{.spec.managementState}'
  Managed
  ```

  — which is exactly why nothing has surfaced yet. The failure chain is structural: rendered
  `helm.sh/hook: pre-delete` + `backoffLimit: 0` + `activeDeadlineSeconds: 120` means one pod
  attempt inside 120s; a pod stuck in ImagePullBackOff never runs the forgiving script; Helm's
  documented uninstall behaviour on a failed pre-delete hook is to error out without deleting the
  release. The chart's own history already measured the failure class: the values comment records
  `registry.redhat.io/openshift4/ose-cli:latest` dying with ErrImagePull in 40s, and the new
  default fails the same way on a `Removed`-registry cluster.
- **Cost if unfixed**: an operator on a bare-metal cluster gets a chart whose *documentation*
  says the image works everywhere, whose install wedges for 300s and fails, and — worse — whose
  uninstall fails too, with no documented way out. The way out (`helm uninstall --no-hooks`, then
  revert by hand) takes one line to write down.
- **REMEDIATION**: three documentation edits, no behaviour change.

  1. `oauth-debug-revert-job.yaml` — replace the comment at lines 44–46 with:

  ```bash
          # NOT `set -e`. A pre-delete hook that fails BLOCKS the uninstall, and an operator trying
          # to remove this chart must never be held hostage by a best-effort tidy-up. Every failure
          # below is reported and then forgiven. That protects against SCRIPT failures only: a pod
          # that never starts (image unreachable, unschedulable) still fails the hook at
          # activeDeadlineSeconds and Helm aborts the uninstall. The escape hatch is
          # `helm uninstall --no-hooks`, then revert the level by hand with the patch below.
          set -uo pipefail
  ```

  2. `values.yaml` — append to the image comment block (after line 605, before `image:`):

  ```yaml
    # ONE CAVEAT: the imagestream exists everywhere, but the internal registry that SERVES this
    # hostname can be absent — platforms without shareable object storage (bare metal, platform
    # "none") bootstrap the image registry operator as `Removed`. There this pull fails, and
    # because Helm aborts on a failed hook, install, upgrade AND uninstall fail with it
    # (uninstall escape hatch: `helm uninstall --no-hooks`). Check with:
    #   oc get configs.imageregistry.operator.openshift.io cluster -o jsonpath='{.spec.managementState}'
    # and override this repository with a mirror your cluster can reach if it is not `Managed`.
  ```

  3. `README.md` — replace the row at line 213 with:

  ```markdown
  | `oauthDebug.revertOnUninstall` | `true` | **leave on.** A pre-delete Job puts the level back, or removing the dashboard leaves the OAuth server naming every person who authenticates with nothing left watching. If the hook itself cannot start (see the image caveat), escape with `helm uninstall --no-hooks` and revert by hand |
  ```
- **Test that would catch a regression**:

  ```python
      def test_the_uninstall_escape_hatch_is_documented(self):
          """A pod that cannot start (the internal registry is `Removed` on bare-metal installs)
          fails the pre-delete hook, and Helm ABORTS an uninstall whose hook fails. The only way
          out is `helm uninstall --no-hooks`, which is useless if no document names it."""
          readme = (CHART / "README.md").read_text()
          values = (CHART / "values.yaml").read_text()
          assert "--no-hooks" in readme, "the wedged-uninstall escape hatch is undocumented"
          assert "Removed" in values, (
              "values.yaml must name the registry-Removed caveat beside the image default"
          )
  ```
- **Risk of the remediation**: none at runtime — comments and docs only. Verify with
  `helm template` (byte-identical manifests apart from comments) and `helm lint`.

> **Codex:** **CONFIRMED** — Red Hat's registry documentation explicitly says platforms without
> shareable object storage bootstrap the Image Registry Operator as `Removed`, including the
> bare-metal/vSphere class named here
> ([OpenShift registry docs](https://docs.redhat.com/en/documentation/openshift_container_platform/4.19/html/registry/configuring-registry-operator#registry-removed-during-installation_configuring-registry-operator)).
> Helm also waits for Job hooks and fails the release when a hook fails
> ([Helm hook lifecycle](https://helm.sh/docs/topics/charts_hooks/)). What the prior remediation
> missed is that `--no-hooks` is an abandonment path, not recovery: it permits uninstall but
> cannot run the revert, so the manual admin patch is mandatory if the CR is still Debug.

### A5. Turning `manage` off while Debug is live strands the cluster, and no document states the off-boarding order

- **Severity**: medium
- **Category**: docs
- **Location**: `charts/group-sync-dashboard/values.yaml:566-577`,
  `charts/group-sync-dashboard/README.md:211`
- **Claim**: The values comment sells `manage: false` as "this chart never touches the cluster's
  setting", and the whole two-switch design exists because "Helm does not run a Job you merely
  stopped rendering" — yet nothing warns that flipping `manage: false` while `enabled: true` is
  live does exactly that: the Job and its RBAC leave the release, nothing runs, and the cluster
  stays in Debug with the chart's means of reverting it deleted. The safe order (set
  `enabled: false`, upgrade, *then* `manage: false`) is stated nowhere.
- **Trigger**: `helm upgrade --set oauthDebug.manage=false` on a release currently at
  `manage=true,enabled=true`. Rendered proof that nothing remains to act:

  ```
  $ helm template t charts/group-sync-dashboard --set ingress.host=t.example.com | grep -c oauth-loglevel
  0
  ```

  (manage=false renders no Job, no SA, no ClusterRole — the existing
  `test_nothing_renders_by_default` pins this, which is precisely why the transition is one-way.)
- **Evidence**: `values.yaml:568` — `manage: false  nothing renders, no RBAC, this chart never
  touches the cluster's setting` — is the complete guidance a reader gets. The Job's own header
  comment (oauth-debug-job.yaml:24-26) explains the mechanism that makes this transition strand
  the cluster, but draws the conclusion only for `enabled`, not for `manage`.
- **Cost if unfixed**: the person off-boarding the feature does the natural thing — turn both
  switches off in one edit — and gets a cluster that silently keeps naming every login, with the
  PII exposure the section's own comments warn about in capitals, and no chart-owned way back.
  They will not notice, because (as the revert Job's header puts it) the thing that would have
  told them is the thing they just turned off.
- **REMEDIATION**: add the order to both documents. In `values.yaml`, insert after line 577
  (before `oauthDebug:`):

  ```yaml
  # TO STOP MANAGING: set `enabled: false` and upgrade FIRST, then set `manage: false`. In that
  # order the Job's last run puts the cluster back to Normal before it leaves the release. In the
  # other order nothing runs — Helm does not run a Job you merely stopped rendering — so Debug
  # stays, and the RBAC that could have reverted it is gone with the Job.
  ```

  In `README.md`, replace the row at line 211 with:

  ```markdown
  | `oauthDebug.manage` | `false` | lets this chart own the cluster's OAuth server log level. Off by default — turning it on is what transfers ownership. To stop managing: `enabled=false` and upgrade **first**, then `manage=false`, or the level strands at Debug with the revert RBAC gone |
  ```
- **Test that would catch a regression**:

  ```python
      def test_the_offboarding_order_is_documented(self):
          """manage:false renders nothing — including the Job that could have put the level
          back. The only safe off-boarding is enabled=false first, manage=false after, and that
          order has to be written where the switches are."""
          values = (CHART / "values.yaml").read_text()
          readme = (CHART / "README.md").read_text()
          assert "TO STOP MANAGING" in values, "values.yaml no longer states the off-boarding order"
          assert "upgrade **first**" in readme, "the README row no longer states the off-boarding order"
  ```
- **Risk of the remediation**: none — documentation only. Verify `helm template` output is
  unchanged and `pytest tests/test_chart_strategy.py` still passes.

> **Codex:** **CONFIRMED** — parsed default output contains zero OAuth objects, while
> `manage=true` contains exactly the SA, ClusterRole, ClusterRoleBinding and two Jobs. Thus a direct
> `manage=false` transition removes every actor capable of convergence. The earlier pass missed the
> most likely operator action: setting *both* flags false in one values edit is just as unsafe as
> changing `manage` alone, so the prose must explicitly require two separate successful upgrades.

### A6. `waitSeconds >= activeDeadlineSeconds` renders unchecked and breaks the "a timeout is not a failure" promise

- **Severity**: low
- **Category**: tech-debt
- **Location**: `charts/group-sync-dashboard/templates/oauth-debug-job.yaml:1` (missing guard);
  the promise is `values.yaml:624` ("Must stay above waitSeconds")
- **Claim**: The design's load-bearing promise is that a slow rollout exits 0 through the
  timeout branch. If `waitSeconds` is set at or above `activeDeadlineSeconds`, the pod is killed
  mid-wait by the Job controller before the branch can run, the Job fails, and `helm upgrade`
  reports FAILED — the exact outcome the comments promise cannot happen. The values comment says
  "Must stay above waitSeconds" but nothing enforces it, and the chart already has a `fail`
  idiom for exactly this class of cross-value constraint (deployment.yaml:2,5,16).
- **Trigger**: `--set oauthDebug.waitSeconds=400` (deadline still 300).
- **Evidence**:

  ```
  $ helm template t charts/group-sync-dashboard --set ingress.host=t.example.com \
      --set oauthDebug.manage=true --set oauthDebug.waitSeconds=400 2>/dev/null \
      | grep -E 'activeDeadlineSeconds|waiting up to'
    activeDeadlineSeconds: 300
            echo "waiting up to 400s for the oauth-openshift rollout"
    activeDeadlineSeconds: 120
  render rc=0
  ```

  A Job that promises to wait 400s inside a 300s wall clock renders without complaint.
- **Cost if unfixed**: whoever raises `waitSeconds` for a slow cluster (the natural knob for the
  natural problem) turns every slow-rollout upgrade into a FAILED release, then spends time
  learning the deadline interaction the values comment only hints at.
- **REMEDIATION**: enforce the constraint at render time, in the chart's own `fail` idiom.
  Replace line 1 of `oauth-debug-job.yaml` (the block below keeps the existing `manage` guard as
  its first line, so the template's structure and its closing `{{- end }}` are unchanged):

  ```yaml
  {{- if .Values.oauthDebug.manage }}
  {{- if ge (int .Values.oauthDebug.waitSeconds) (int .Values.oauthDebug.activeDeadlineSeconds) }}
  {{- fail "oauthDebug.waitSeconds must be below oauthDebug.activeDeadlineSeconds. The deadline is a wall clock on the WHOLE pod — image pull, patch and wait — so a wait that reaches it is killed by the Job controller before its graceful-timeout branch can run: the Job fails and `helm upgrade` reports FAILED, which is exactly what the 'a timeout is not a failure' design promises cannot happen. The defaults (180 < 300) leave 120s of headroom; keep some." }}
  {{- end }}
  ```

  (The second `if` sits inside the existing `manage` guard, so a misconfigured-but-unused value
  set does not block a render that would never run the Job.)
- **Test that would catch a regression**:

  ```python
      def test_a_wait_longer_than_the_deadline_is_refused(self):
          """activeDeadlineSeconds is a wall clock on the whole pod. A waitSeconds at or above
          it means the Job controller kills the pod mid-wait and `helm upgrade` reports FAILED —
          contradicting the documented 'a timeout is not a failure' design."""
          ok, out = render(**self.ON, oauthDebug__waitSeconds="400")
          assert not ok, "waitSeconds above activeDeadlineSeconds must refuse to render"
          assert "waitSeconds" in out
  ```
- **Risk of the remediation**: a values file that previously rendered (and misbehaved) now fails
  the render — that is the point, and the message says what to change. Defaults pass
  (`180 < 300`). Verify: `helm template` with defaults renders; with `waitSeconds=400` it fails
  with the message; `helm lint` still passes.

> **Codex:** **FIX-INADEQUATE** — render-time `fail` is the right mechanism, and A6/B2 are semantic
> duplicates, but strict `<` does not enforce their stated promise. In a scratch chart the proposed
> guard correctly rejected 300/300 and 400/300 and allowed 600/720, yet it also allowed 299/300.
> Kubernetes applies `activeDeadlineSeconds` to the whole Job lifetime and marks it
> `DeadlineExceeded` when reached
> ([Kubernetes Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/#active-deadline-seconds));
> one second cannot cover scheduling, image pull, the reads and patch before the loop starts. Enforce
> an explicit minimum headroom (the defaults provide 120s), or weaken the “timeout is not a failure”
> promise. The guard belongs inside `manage`, as proposed.

### A7. The wait loop's `get deployments` grant is cluster-wide for a loop that reads exactly one Deployment

- **Severity**: low
- **Category**: rbac
- **Location**: `charts/group-sync-dashboard/templates/oauth-debug-rbac.yaml:40-42` (shared
  territory with Reviewer B — filed here because the grant exists solely to serve the Jobs' wait
  loop)
- **Claim**: The `apps/deployments get` rule carries no `resourceNames`, so the Job's SA can read
  every Deployment in every namespace. Every `oc get` in both Jobs targets one name,
  `oauth-openshift`, and `get` is a named verb for which `resourceNames` is honoured — the same
  fact the rule above it leans on for `patch`. The rbac file's own header standard ("the smallest
  thing that buys it", per the sibling users-grant test) argues for the pin.
- **Trigger**: any namespace, any deployment:
- **Evidence**:

  ```
  $ SA=system:serviceaccount:group-sync-dashboard:group-sync-dashboard-oauth-loglevel
  $ oc auth can-i get deployments -n kube-system --as=$SA
  yes
  $ oc auth can-i get deployments/oauth-openshift -n openshift-authentication --as=$SA
  yes
  ```

  The second line also proves the pinned form still satisfies the loop.
- **Cost if unfixed**: no write exposure, but the next reviewer of the chart's RBAC (this repo
  demonstrably has those) finds a cluster-wide read on a chart that documents itself as
  minimal-grant, and burns time confirming it is benign — or worse, cites it as precedent.
- **REMEDIATION**: replace the second rule in the ClusterRole with:

  ```yaml
    # Read-only, and only to answer "has the rollout finished?" — see the wait loop in the Job, and
    # why `oc rollout status` cannot be trusted for it. Pinned to the one Deployment the loop
    # reads: `get` is a named verb, so resourceNames is honoured here just as it is for `patch`
    # above. (The pin is by NAME, not namespace — good enough: reading a Deployment named
    # oauth-openshift is only meaningful in openshift-authentication.)
    - apiGroups: ["apps"]
      resources: ["deployments"]
      resourceNames: ["oauth-openshift"]
      verbs: ["get"]
  ```

  And update the matching row in `docs/reference-architecture.md`'s separate-ClusterRole table:
  `| apps | deployments, resourceNames: [oauth-openshift] | get |`.
- **Test that would catch a regression**:

  ```python
      def test_the_rollout_read_is_pinned_to_the_one_deployment_it_reads(self):
          """`get` is a named verb, so resourceNames is honoured — unpinned, the Job's SA can
          read every Deployment in every namespace (measured: `oc auth can-i get deployments
          -n kube-system --as=<the SA>` => yes) for a loop that only ever reads oauth-openshift."""
          ok, out = render(**self.ON)
          assert ok, out
          rules = [r for d in self._docs(out)
                   if d.get("kind") == "ClusterRole" and "oauth-loglevel" in d["metadata"]["name"]
                   for r in d["rules"] if "deployments" in (r.get("resources") or [])]
          assert len(rules) == 1, f"expected exactly one deployments rule, got {len(rules)}"
          assert rules[0].get("resourceNames") == ["oauth-openshift"], (
              f"the rollout read must be pinned to the Deployment the loop reads: {rules[0]}"
          )
  ```
- **Risk of the remediation**: none to the Jobs — every read is `get deploy oauth-openshift`,
  which the pinned rule permits (proven by the `can-i` line above). Verify post-change with the
  same two `oc auth can-i` probes: the kube-system one must flip to `no`
  (`can-i get deployments -n kube-system` without a name is an unnamed get, which a
  resourceNames rule no longer satisfies), the named one must stay `yes`.

> **Codex:** **CONFIRMED** — the parsed managed render has exactly one Deployment rule and it is
> `apiGroups:[apps], resources:[deployments], verbs:[get]` with no `resourceNames`; all five Job
> reads name `oauth-openshift`. Kubernetes RBAC permits `resourceNames` restrictions for named
> requests, so the pin is valid
> ([Kubernetes RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/#referring-to-resources)).
> What the earlier passes under-emphasized is the remainder: a ClusterRole cannot bind the namespace,
> so the fixed grant still reads a Deployment named `oauth-openshift` in any namespace. B3's wording
> discloses that accurately; A7's comment should too.

### A8. The apply Job outlives `helm uninstall` and no comment says so

- **Severity**: low
- **Category**: docs
- **Location**: `charts/group-sync-dashboard/templates/oauth-debug-job.yaml:37-40`
- **Claim**: The delete-policy comment says the Job's log is "worth keeping until the next
  upgrade", implying its lifecycle ends there. Helm never deletes hook resources on uninstall
  (documented Helm 3 behaviour — hooks are not tracked as release resources), and this Job's only
  delete policy is `before-hook-creation`, so after `helm uninstall` the completed Job and its
  pod remain in the namespace indefinitely. The revert Job self-cleans (`hook-succeeded`); this
  one does not, deliberately — but the uninstall case is unstated.
- **Trigger**: `helm uninstall` of a release that ran the Job at least once (not runnable here —
  live shared cluster — the mechanism is Helm-documented and the current cluster already shows
  the standing Job that would be orphaned).
- **Evidence**: the Job and pod exist right now, owned only by hook policy:

  ```
  $ oc get jobs -A | grep -i loglevel
  group-sync-dashboard   group-sync-dashboard-oauth-loglevel   Complete   1/1   18s   2m27s
  $ oc get pods -A | grep -i loglevel
  group-sync-dashboard   group-sync-dashboard-oauth-loglevel-6fkmx   0/1   Completed   0   2m27s
  ```

  Rendered policy: `helm.sh/hook-delete-policy: before-hook-creation` — nothing fires on
  uninstall, and Helm's uninstall does not touch hook-created resources.
- **Cost if unfixed**: small and singular — a stale completed Job in a namespace months after the
  release is gone, found by whoever audits the namespace next, plus one puzzled retracing of this
  exact reasoning. Keeping the log is a fair trade; the trade should be written down.
- **REMEDIATION**: replace the comment at lines 37–39 with:

  ```yaml
      # before-hook-creation, so an upgrade replaces the previous run rather than failing on a name
      # that already exists. NOT hook-succeeded: the log of what this changed on the cluster is worth
      # keeping until the next upgrade. The known trade: Helm never deletes hook resources on
      # uninstall, so the last run's completed Job outlives the release — harmless residue, gone the
      # next time a release of this name installs, or with one `oc delete job`.
  ```
- **Test that would catch a regression** (template comments render verbatim — the
  `TestNoPatchVerbAtAnyAuditMode` docstring already relies on this):

  ```python
      def test_the_apply_jobs_uninstall_residue_is_acknowledged(self):
          """Helm never deletes hook resources on uninstall, and this Job's only delete policy
          is before-hook-creation: the last run outlives the release. Deliberate — so the comment
          beside the policy has to say so, or the next auditor retraces this from scratch."""
          ok, out = render(**self.ON)
          assert ok, out
          assert "outlives the release" in out, (
              "the delete-policy comment no longer states the uninstall residue trade-off"
          )
  ```
- **Risk of the remediation**: none — comment only. Verify manifests are byte-identical apart
  from the comment (`helm template | grep -v '^#'` diff) and lint passes.

> **Codex:** **CONFIRMED** — Helm explicitly states hook resources are not tracked with the release
> and cannot be assumed removed by uninstall
> ([Helm hook resources](https://helm.sh/docs/topics/charts_hooks/#hook-resources-are-not-managed-with-corresponding-releases)).
> The rendered apply Job has only `before-hook-creation`; the revert Job alone adds
> `hook-succeeded`. The previous passes missed one useful precision: “next install replaces it” is
> true only for the same rendered Job name, so the comment should say “next install of the same
> release name,” not any release.

## Sound as built

- **The two-switch convergence at install/upgrade** — rendered all four (manage, enabled)
  combinations: `manage=false` renders zero `oauth-loglevel` objects; `manage=true` renders
  `WANT=Normal`/`WANT=Debug` per `enabled` (the shipped tests pin both), and the live cluster's
  Job log shows the Debug→Normal direction actually executing. The remaining convergence gaps are
  F2 (rollback) and F5 (manage-off order), filed above.
- **The write grant's pin does what the comments claim** — probed with `oc auth can-i --as=` the
  Job's real SA: `patch authentications.operator.openshift.io/cluster` → yes; unnamed `patch`,
  `create`, `delete` → no. `resourceNames` is honoured for `patch` exactly as documented.
- **Pre-delete ordering** — the revert Job's SA/binding are regular release resources, and Helm
  deletes those after pre-delete hooks complete (given measured fact, consistent with the
  rendered `helm.sh/hook: pre-delete` and the absence of `resource-policy: keep`); the
  `-revert` name suffix means the two Jobs can never collide.
- **The pod spec actually runs** — checked the completed pod on the live cluster: admitted under
  `restricted-v2`, SCC-assigned `runAsUser: 1000670000` (the imagestream's image declares no
  USER — `oc get istag -n openshift cli:latest -o jsonpath='{...Config.User}'` is empty — so
  `runAsNonRoot` is satisfied by SCC mutation, fine on the OpenShift-only target),
  `readOnlyRootFilesystem: true` with `HOME=/tmp` and no writable volume, exit code 0 in 13s.
  Bash, `date +%s`, `sleep` and `oc`'s in-cluster auth all demonstrably work in that image under
  that lockdown; `oc`'s discovery-cache writes to an unwritable HOME are best-effort and
  non-fatal, as the successful run shows.
- **The shell modes are each right for their Job** — `set -euo pipefail` in the apply Job makes a
  failed patch fail the upgrade (the correct signal, retried by `backoffLimit: 2`, idempotent on
  re-run); `set -uo pipefail` + unconditional `exit 0` in the revert Job keeps script failures
  from blocking uninstall. The one shared hole in both (the read shortcut) is F3.
- **Empty-jsonpath and missing-object handling in the loop** — every numeric comparison guards
  with `${var:-default}`, so a present-but-empty status field becomes 0/1 rather than a test
  error; a missing Deployment or a 403 yields `gen=0`/`obs=-1`, which can never satisfy
  `obs == gen`, so the loop degrades to the benign timeout branch (verified by tracing each
  `|| echo` default through the condition; bash `echo -1` prints `-1`, not an option error).
- **Deadline interactions at defaults** — `waitSeconds=180 < activeDeadlineSeconds=300` leaves
  120s for pull+patch; revert is `backoffLimit: 0` inside 120s, so an uninstall is bounded.
  The unguarded non-default combination is F6.
- **Rendering hygiene** — `helm lint` passes with the feature on; `pytest
  tests/test_chart_strategy.py` → 30 passed on this checkout; the new tests live in the one file
  CI's `chart` job runs by path.


---

# Reviewer B — RBAC, values, docs, tests

## Verdict

Shippable after three fixes; the design itself is sound and the live-cluster probes confirm the RBAC pin does exactly what the docs claim. The single most important change is F1: the central constraint — the dashboard can never hold the write — is guarded only on the *role* side, and a one-line rebinding of the write ClusterRole to the dashboard's ServiceAccount passes all 30 tests while the README claims `test_chart_strategy.py` would fail. Second is F2 (an unenforced `waitSeconds`/`activeDeadlineSeconds` ordering that turns the documented "a timeout is not a failure" into a failed `helm upgrade`), third is F3 (the `deployments get` grant is cluster-wide for a loop that reads exactly one object). Every proposed test below was verified to pass on the fixed chart and to fail under the specific mutation it exists to catch; the current suite let seven such mutations through.

All verification was done against scratchpad copies (`.../scratchpad/mut/`, `.../scratchpad/fixed/`) and read-only `oc auth can-i` on the live CRC cluster — the repo working tree and the cluster were not modified.

## Findings and remediation

### B1. The write role's *binding* is untested — rebinding it to the dashboard SA passes every test
- **Severity**: high
- **Category**: test-quality
- **Location**: local-development/tests/test_chart_strategy.py:154-256 (the class); charts/group-sync-dashboard/README.md:237-239 (the claim it falsifies)
- **Claim**: `test_the_dashboards_own_role_never_gains_the_write` checks ClusterRole *rules* and deliberately skips any role named `oauth-loglevel`, and `test_the_jobs_write_is_pinned_to_one_named_object` checks the rule shape — but nothing anywhere asserts *who the write role binds to*. Changing the ClusterRoleBinding subject from the Job's SA to the dashboard's SA hands the dashboard `patch` on the cluster's authentication config with the whole suite green, while README.md:237-239 states "The dashboard's own role stays read-only, and `test_chart_strategy.py` fails if that ever stops being true."
- **Trigger**: in `oauth-debug-rbac.yaml`, change the ClusterRoleBinding subject `name: {{ include "gsd.fullname" . }}-oauth-loglevel` to `name: {{ include "gsd.serviceAccountName" . }}`.
- **Evidence**: mutation M2, run against a scratch copy of the chart + test file:
  ```
  [M2 bind ClusterRole to DASHBOARD SA] 6 passed in 1.38s     <- current tests
  [M2 bind write role to dashboard SA] 1 failed, 10 passed    <- with the test below
  ```
  Control mutations (remove `resourceNames` pin, render by default, reader role gains patch) all failed the current tests, so the harness is honest.
- **Cost if unfixed**: the one regression the feature exists to prevent — the dashboard holding a platform write — ships silently the day someone "simplifies" the RBAC to one ServiceAccount, and five documents' claims go false with no red test.
- **REMEDIATION**: add to `TestTheOauthLogLevelJobKeepsTheWriteOffTheDashboard` (after `test_the_jobs_write_is_pinned_to_one_named_object`):

  ```python
      def test_the_write_role_is_bound_only_to_the_jobs_own_serviceaccount(self):
          """The role test above is not enough on its own: rebinding the write role to the
          DASHBOARD's ServiceAccount hands it the patch without touching any ClusterRole, and
          that is the escalation the whole file exists to prevent."""
          ok, out = render(**self.ON)
          assert ok, out
          docs = self._docs(out)
          job_sa = [d["metadata"]["name"] for d in docs if d.get("kind") == "ServiceAccount"
                    and "oauth-loglevel" in d["metadata"]["name"]]
          assert len(job_sa) == 1, "the Job's own ServiceAccount is missing"
          bindings = [d for d in docs if d.get("kind") == "ClusterRoleBinding"
                      and "oauth-loglevel" in d["roleRef"]["name"]]
          assert len(bindings) == 1, "expected exactly one binding of the write role"
          subjects = bindings[0]["subjects"]
          assert [(x.get("kind"), x.get("name")) for x in subjects] == \
              [("ServiceAccount", job_sa[0])], (
              f"the write role must bind ONLY the Job's own ServiceAccount, got {subjects}"
          )
  ```
- **Test that would catch a regression**: the remediation IS the test. Verified: passes on the current chart (the binding is correct as built), fails under M2 (`1 failed, 10 passed`).
- **Risk of the remediation**: none to the chart — pure test addition. The name-substring matching follows the existing class idiom; a deliberate rename of the component would fail this test loudly, which is the intended behaviour.

> **Codex:** **FIX-INADEQUATE** — I made the stated one-line subject mutation in a scratch chart:
> all **30/30** current tests passed. Adding the proposed test made that mutation fail (`1 failed,
> 6 passed` for this class), and the unmutated chart passed (`7 passed`). But the proposed assertion
> drops `subject.namespace`: changing it to `other-namespace` still passed all seven class tests.
> More seriously, it renders only the default dashboard SA name. A supported value can set
> `serviceAccount.name` equal to the fixed `*-oauth-loglevel` name; the render then contains two
> same-named ServiceAccounts, the dashboard Deployment uses that identity, and the write binding
> grants it `patch`. The earlier passes missed this configuration-level bypass. The test must assert
> the exact subject triple `(kind, name, namespace)` and test that the chart refuses that collision.

### B2. `waitSeconds >= activeDeadlineSeconds` renders happily and fails the upgrade the docs promise it won't
- **Severity**: medium
- **Category**: correctness
- **Location**: charts/group-sync-dashboard/templates/oauth-debug-job.yaml:1 (missing guard); charts/group-sync-dashboard/values.yaml:624 ("Must stay above waitSeconds" — documented, unenforced)
- **Claim**: `waitSeconds` exists precisely so slow clusters can raise it, but raising it past `activeDeadlineSeconds` (default 300) is accepted silently; the deadline then kills the pod mid-wait, the Job fails, and a failed post-upgrade hook fails `helm upgrade` — even though the patch landed. That is exactly the outcome the script's exit-0 timeout and the values comment ("A timeout here is NOT a failure") promise cannot happen.
- **Trigger**: `--set oauthDebug.manage=true --set oauthDebug.waitSeconds=600` (deadline left at its 300 default) on any cluster whose oauth rollout takes over 300s.
- **Evidence**:
  ```
  $ helm template t charts/group-sync-dashboard --set ingress.host=t.example.com \
      --set oauthDebug.manage=true --set oauthDebug.waitSeconds=600 | grep -E "activeDeadline|waiting up to"
    activeDeadlineSeconds: 300
            echo "waiting up to 600s for the oauth-openshift rollout"
  ```
  Renders with no complaint. The chart already refuses impossible value combinations elsewhere in exactly this idiom (`deployment.yaml:2,5,16` — three `fail` guards).
- **Cost if unfixed**: a GitOps or CI upgrade fails with a hook error on a healthy cluster; whoever debugs it reads "Job ... DeadlineExceeded", concludes the feature is broken, and burns time re-deriving what the values comment already knew.
- **REMEDIATION**: insert directly after line 1 of `charts/group-sync-dashboard/templates/oauth-debug-job.yaml`:

  ```yaml
  {{- if .Values.oauthDebug.manage }}
  {{- if ge (int .Values.oauthDebug.waitSeconds) (int .Values.oauthDebug.activeDeadlineSeconds) }}
  {{- fail "oauthDebug.waitSeconds must stay below oauthDebug.activeDeadlineSeconds. The deadline is the wall clock on the WHOLE attempt: reached, it kills the pod and fails the Job, and a failed post-upgrade hook fails `helm upgrade` — which turns the documented 'a wait timeout is not a failure' into exactly the failure it promises to avoid. Raise activeDeadlineSeconds alongside waitSeconds, keeping headroom for scheduling and the patch itself." }}
  {{- end }}
  ```
  (The first line shown is the existing line 1, for placement; the guard is the three lines under it.)
- **Test that would catch a regression**:

  ```python
      def test_a_wait_longer_than_the_deadline_is_refused(self):
          """waitSeconds above activeDeadlineSeconds is a Job the deadline kills mid-wait: the
          Job fails, so the post-upgrade hook fails, so `helm upgrade` fails — the exact outcome
          the wait's exit-0 timeout exists to avoid."""
          ok, out = render(**self.ON, oauthDebug__waitSeconds="600")
          assert not ok, "renders a wait the deadline is guaranteed to kill"
          assert "waitSeconds" in out
          ok, _ = render(**self.ON, oauthDebug__waitSeconds="600",
                         oauthDebug__activeDeadlineSeconds="720")
          assert ok, "raising the deadline alongside the wait must stay allowed"
  ```
  Verified: fails on the current chart (`assert not ok` — it renders), passes with the guard. Guard verified to emit the message and to still render 600/720; `helm lint` clean.
- **Risk of the remediation**: a user currently running an (already-broken) `waitSeconds >= activeDeadlineSeconds` combination gets a render failure on their next upgrade instead of a hook failure — that is the guard doing its job, and the message tells them the fix. `ge` on `(int ...)` casts matches how Helm coerces `--set` numerics; verified with both `--set` and default values.

> **Codex:** **FIX-INADEQUATE** — this duplicates A6. The proposed guard and its 600/720 positive
> test both worked in a scratch chart and `helm lint` stayed clean, but the same guard accepts
> 299/300. `activeDeadlineSeconds` covers the complete Job, not just the scripted loop, so that does
> not make the graceful timeout reachable after scheduling, pull, API reads, and patching. Keep one
> guard, inside `manage`, with a stated minimum headroom; do not apply both A6 and B2 patches.

### B3. `apps/deployments get` is cluster-wide for a loop that reads one Deployment in one namespace
- **Severity**: medium
- **Category**: rbac
- **Location**: charts/group-sync-dashboard/templates/oauth-debug-rbac.yaml:40-42
- **Claim**: the wait loop reads only `deploy/oauth-openshift` in `openshift-authentication`, but the rule grants `get` on every Deployment in every namespace — probed and confirmed against the live cluster. Read-only, but wider than its purpose, and unpinned while the rule directly above it demonstrates the pinning idiom.
- **Trigger**: `oc auth can-i get deployments.apps -n <any namespace> --as=system:serviceaccount:group-sync-dashboard:group-sync-dashboard-oauth-loglevel`
- **Evidence** (live CRC, feature deployed):
  ```
  a) get deploy in openshift-authentication: yes
  b) get deploy in kube-system:              yes
  c) get deploy in openshift-console:        yes
  d) get deploy in ALL namespaces:           yes
  e) list deploy:                            no
  f) patch deploy:                           no
  ```
- **Cost if unfixed**: an RBAC audit flags a hook ServiceAccount that can read every workload spec on the cluster (images, env var names, annotations) for a feature whose whole pitch is minimal separation; somebody then spends a review cycle re-litigating a grant that never needed the width.
- **REMEDIATION**: on the question "is a ClusterRole even the right kind?" — semantically a Role in `openshift-authentication` is the right kind, but it would put a release resource in a namespace this chart does not own (friction with the chart's ArgoCD support, which must then permit a second destination namespace). The minimal fix in the file's own idiom is the name pin, which RBAC honours for `get` exactly as it does for `patch`. Replace lines 38-42 of `oauth-debug-rbac.yaml`:

  ```yaml
    # Read-only, and only to answer "has the rollout finished?" — see the wait loop in the Job, and
    # why `oc rollout status` cannot be trusted for it. Name-pinned like the rule above; the
    # namespace cannot be pinned from a ClusterRole, and a Role in openshift-authentication would
    # put a release resource in a namespace this chart does not own — so `get` on one deployment
    # NAME, anywhere, is the accepted remainder.
    - apiGroups: ["apps"]
      resources: ["deployments"]
      resourceNames: ["oauth-openshift"]
      verbs: ["get"]
  ```
- **Test that would catch a regression**: covered by F7's exact-rules test (which pins `resourceNames: ["oauth-openshift"]` on this rule). Verified: that test fails on the current unpinned chart and passes with this remediation applied.
- **Risk of the remediation**: none functional — the wait loop only ever `get`s that name (`oauth-debug-job.yaml:103-112`), and `resourceNames` with `get` is core RBAC behaviour (same mechanism the live probes above validated for `patch`/`get` on `authentications`). Verify after applying with the same `can-i` probes: (a) stays `yes`, (b)-(d) become `yes` only for the name `oauth-openshift`.

> **Codex:** **CONFIRMED** — parsed rendered YAML shows the Deployment rule has `get` with no
> `resourceNames`, while every scoped Job read names `oauth-openshift`. Kubernetes documents that a
> `resourceNames` list restricts named `get` requests
> ([RBAC documentation](https://kubernetes.io/docs/reference/access-authn-authz/rbac/#referring-to-resources)).
> What the prior passes still missed is the accepted remainder: ClusterRole cannot restrict
> namespace, so the fixed role can still read that name anywhere. Apply
> either A7 or B3, not both; B3's comment states the remainder more clearly.

### B4. The "both ways" test pins the WANT *assignment*, not the patch — a hardcoded one-way Job passes
- **Severity**: medium
- **Category**: test-quality
- **Location**: local-development/tests/test_chart_strategy.py:216-225 (`test_the_job_applies_the_REQUESTED_level_both_ways`)
- **Claim**: the test asserts `"WANT=Normal" in off` and `"WANT=Debug" in on`, which only proves the shell variable is assigned — the `oc patch` payload is unchecked, so hardcoding `Debug` in the patch recreates the exact one-way-enable regression the test's own docstring names, with the test green. The wait loop's target deployment is equally unchecked, so a typo there silently costs 180s per upgrade before claiming success.
- **Trigger**: change `-p "{\"spec\":{\"logLevel\":\"${WANT}\"}}"` to `-p "{\"spec\":{\"logLevel\":\"Debug\"}}"` in oauth-debug-job.yaml (M1); or typo `oc get deploy oauth-opensift` (M7).
- **Evidence**:
  ```
  [M1 hardcode Debug in patch payload] 6 passed in 1.58s      <- current tests
  [M7 wait loop polls wrong deployment name] 6 passed in 1.43s
  [M1 hardcoded Debug payload] 1 failed, 10 passed            <- with the fix below
  [M7 typo wait-loop deployment] 1 failed, 10 passed
  ```
- **Cost if unfixed**: the test is a claim of coverage for the feature's marquee property ("turn it off works") that would not fail when that property regresses — worse than no test, per the review bar.
- **REMEDIATION**: replace the body of `test_the_job_applies_the_REQUESTED_level_both_ways` (keep the docstring):

  ```python
          payload = r'-p "{\"spec\":{\"logLevel\":\"${WANT}\"}}"'
          ok, off = render(**self.ON)
          assert ok and "WANT=Normal" in off, "with enabled=false the Job must request Normal"
          assert payload in off, "the patch must apply ${WANT}, not a hardcoded level"
          assert "oc get deploy oauth-openshift -n openshift-authentication" in off, (
              "the wait loop must poll the deployment the RBAC comment names, or it times out "
              "silently on every upgrade"
          )
          ok, on = render(**self.ON, oauthDebug__enabled="true")
          assert ok and "WANT=Debug" in on, "with enabled=true the Job must request Debug"
          assert payload in on, "the patch must apply ${WANT}, not a hardcoded level"
  ```
- **Test that would catch a regression**: the remediation is the test. Verified: passes on the current chart, fails under M1 and M7.
- **Risk of the remediation**: the assertions bind to the script's exact text, so a legitimate rewording of the patch line breaks the test — acceptable here because the payload string IS the behaviour under test, and the failure message says what to update.

> **Codex:** **CONFIRMED** — the prior report understated the gap: both the hardcoded-`Debug` patch
> mutation and the misspelled wait target passed the entire current suite, **30/30**, not merely six
> selected tests. The proposed assertions fail for each mutation and pass on current output. They are
> intentionally text-coupled; after A1/D2 replaces the wait implementation, update this test to pin
> the rendered patch payload and the new direct desired-verbosity/full-rollout query instead of the
> obsolete command spelling.

### B5. The revert Job's payload is untested — a revert that patches `Debug` passes
- **Severity**: medium
- **Category**: test-quality
- **Location**: local-development/tests/test_chart_strategy.py:227-239 (`test_uninstall_reverts_by_default`)
- **Claim**: the revert test checks the Job exists and is `pre-delete`, but never that it puts the level back to `Normal`. The one line that is the revert's entire purpose can invert and the suite stays green.
- **Trigger**: change the revert's `-p '{"spec":{"logLevel":"Normal"}}'` to `"Debug"` (M6).
- **Evidence**:
  ```
  [M6 revert Job patches Debug not Normal] 6 passed in 1.38s   <- current tests
  [M6 revert patches Debug] 1 failed, 10 passed                <- with the test below
  ```
- **Cost if unfixed**: the uninstall path is the one nobody watches (the doc's own words: "the thing that would have told you is the thing you just removed") — a regression here leaves clusters logging every login's DN indefinitely, discovered only by audit.
- **REMEDIATION**: add to the class:

  ```python
      def test_the_revert_job_puts_the_level_back_to_Normal(self):
          """pre-delete alone is not the behaviour — the payload is. A revert Job that patched
          anything but Normal would pass every other test here."""
          ok, out = render(**self.ON)
          assert ok, out
          jobs = [d for d in self._docs(out)
                  if d.get("kind") == "Job" and d["metadata"]["name"].endswith("-revert")]
          assert len(jobs) == 1, "the pre-delete revert Job is missing"
          script = jobs[0]["spec"]["template"]["spec"]["containers"][0]["command"][-1]
          assert '{"spec":{"logLevel":"Normal"}}' in script, (
              "the revert Job must patch the level back to Normal"
          )
  ```
  (Parsing the YAML and reading `command[-1]` distinguishes the real patch — clean quotes — from the escaped `\"Normal\"` in the fallback echo text, so the assertion cannot be satisfied by the help message.)
- **Test that would catch a regression**: the remediation is the test. Verified pass-on-current / fail-under-M6.
- **Risk of the remediation**: none — additive, parses rendered YAML in the class's existing style.

> **Codex:** **CONFIRMED** — changing only the revert payload from `Normal` to `Debug` passed all
> **30/30** current tests. I parsed the rendered container script: the real payload contains one clean
> `{"spec":{"logLevel":"Normal"}}`, while the fallback help text is escaped, so the proposed
> `command[-1]` assertion distinguishes them and fails the mutation. The prior passes missed that the
> same mutation survives every test in the file, not just the feature class subset.

### B6. The set Job's hook annotations are untested — stripping them passes, and breaks every later upgrade
- **Severity**: medium
- **Category**: test-quality
- **Location**: local-development/tests/test_chart_strategy.py (no test); charts/group-sync-dashboard/templates/oauth-debug-job.yaml:35-40 (the annotations)
- **Claim**: nothing asserts `helm.sh/hook: post-install,post-upgrade` or the `before-hook-creation` delete policy on the set Job. Without the hook annotation the Job becomes a regular release resource: it runs once at install, an `enabled` flip re-renders an *immutable* Job spec and the upgrade errors, and the two-switch convergence design silently stops existing.
- **Trigger**: delete the `annotations:` block from oauth-debug-job.yaml metadata (M5).
- **Evidence**:
  ```
  [M5 strip hook annotations from set Job] 6 passed in 1.37s   <- current tests
  [M5 strip hook annotations] 1 failed, 10 passed              <- with the test below
  ```
- **Cost if unfixed**: the failure arrives one upgrade later than the edit that caused it, as a cryptic `field is immutable` error on a Job nobody remembers is load-bearing.
- **REMEDIATION**: add to the class:

  ```python
      def test_the_set_job_is_a_hook_that_reruns_on_every_upgrade(self):
          """Lose the hook annotation and the Job becomes a regular release resource: it runs
          once at install, `enabled` flips never converge, and the next upgrade trips over the
          immutable Job spec."""
          ok, out = render(**self.ON)
          assert ok, out
          jobs = [d for d in self._docs(out) if d.get("kind") == "Job"
                  and d["metadata"]["name"].endswith("-oauth-loglevel")]
          assert len(jobs) == 1, "the set Job is missing"
          ann = jobs[0]["metadata"].get("annotations") or {}
          assert ann.get("helm.sh/hook") == "post-install,post-upgrade", ann
          assert ann.get("helm.sh/hook-delete-policy") == "before-hook-creation", ann
  ```
- **Test that would catch a regression**: the remediation is the test. Verified pass-on-current / fail-under-M5.
- **Risk of the remediation**: pins the delete policy exactly, so a deliberate policy change must touch the test — intended, since the current policy is documented as deliberate ("NOT hook-succeeded") in the template.

> **Codex:** **FIX-INADEQUATE** — deleting the annotation block passed all **30/30** current tests,
> so the missing coverage is real. However, A2 correctly adds `post-rollback`; this proposed exact
> equality would then reject the repaired hook. Apply A2 first and assert the hook set is exactly
> `{post-install, post-upgrade, post-rollback}` (normalizing the comma-separated value), while keeping
> the exact `before-hook-creation` check. B6 as written and A2 are incompatible.

### B7. The Job role's total surface is unbounded by tests — extra rules and widened apiGroups ride through
- **Severity**: medium
- **Category**: test-quality
- **Location**: local-development/tests/test_chart_strategy.py:184-201 (`test_the_jobs_write_is_pinned_to_one_named_object`)
- **Claim**: the pin test filters for rules containing `authentications` and never asserts `apiGroups`, so widening the rule to `["operator.openshift.io", "config.openshift.io"]` (patch on the cluster's *identity-provider* config, `authentications.config.openshift.io`) passes; and a wholly new rule (e.g. secrets get/list) added to the same ClusterRole is invisible to every test, because the dashboard-role test skips anything named `oauth-loglevel`.
- **Trigger**: M3 (widen apiGroups) or M4 (append a secrets rule) in oauth-debug-rbac.yaml.
- **Evidence**:
  ```
  [M3 widen apiGroups to config.openshift.io too] 6 passed in 1.37s   <- current tests
  [M4 add secrets rule to Job ClusterRole] 6 passed in 1.72s
  [M3 widen apiGroups] 1 failed, 10 passed                            <- with the test below
  [M4 extra secrets rule] 1 failed, 10 passed
  ```
- **Cost if unfixed**: the write-side ServiceAccount is the feature's privileged surface; the name-based exemption in the dashboard test means it is precisely the place a widening lands unnoticed.
- **REMEDIATION**: add to the class (rules shown as they stand after F3's pin; drop the second `resourceNames` line if F3 is rejected):

  ```python
      def test_the_jobs_role_carries_nothing_beyond_its_two_audited_rules(self):
          """Every rule, pinned exactly. The named-object test above bounds the authentications
          rule but says nothing about rules ADDED next to it — a secrets read or a widened
          apiGroups list would ride in unnoticed."""
          ok, out = render(**self.ON)
          assert ok, out
          roles = [d for d in self._docs(out) if d.get("kind") == "ClusterRole"
                   and "oauth-loglevel" in d["metadata"]["name"]]
          assert len(roles) == 1, "expected exactly one oauth-loglevel ClusterRole"
          assert roles[0]["rules"] == [
              {"apiGroups": ["operator.openshift.io"], "resources": ["authentications"],
               "resourceNames": ["cluster"], "verbs": ["get", "patch"]},
              {"apiGroups": ["apps"], "resources": ["deployments"],
               "resourceNames": ["oauth-openshift"], "verbs": ["get"]},
          ], f"the Job role widened beyond its audited surface: {roles[0]['rules']}"
  ```
- **Test that would catch a regression**: the remediation is the test. Verified pass-on-fixed / fail-under-M3-and-M4 (and fail on the current chart until F3's pin lands — which is the "fails before the fix" property for F3).
- **Risk of the remediation**: an exact-match pin means any deliberate rule change edits this test too — that is the point; the assertion message prints the diff.

> **Codex:** **CONFIRMED** — independently adding `config.openshift.io` to `apiGroups` and adding a
> secrets `get/list` rule each passed **30/30** current tests. The proposed exact parsed-rule assertion
> fails both. What the prior passes missed is ordering: it intentionally fails the current chart until
> A7/B3 adds the Deployment name pin, so apply that RBAC fix first, then land this test.

### B8. The off-ramp order is undocumented — one-step `manage=false` strands the cluster in Debug with the revert gone too
- **Severity**: medium
- **Category**: docs
- **Location**: charts/group-sync-dashboard/README.md:226-243 (section); charts/group-sync-dashboard/values.yaml:561-577 (two-switches comment)
- **Claim**: every doc explains why `enabled=false` must run a Job, but none states the operational consequence: to stop, you must set `enabled=false` and **upgrade first**, and only then (optionally) `manage=false`. Going straight to `manage=false` — the intuitive one-step "turn this whole thing off" — removes the Job, the RBAC *and* the pre-delete revert without ever patching, so the cluster stays in Debug and even a later `helm uninstall` no longer fixes it.
- **Trigger**: `helm upgrade ... --set oauthDebug.manage=false` while the cluster is at `Debug`. Nothing renders (verified: default render contains zero `oauth-loglevel` strings), so no Job runs, and `spec.logLevel` stays `Debug`.
- **Evidence**:
  ```
  $ helm template t charts/group-sync-dashboard --set ingress.host=t.example.com | grep -c oauth-loglevel
  0
  ```
  With `manage=false` the revert Job template is also gated out (`oauth-debug-revert-job.yaml:1` requires `and .manage .revertOnUninstall`), so the uninstall safety net disappears with the same flag flip.
- **Cost if unfixed**: an operator who "turned the feature off" leaves the OAuth server naming every login plus LDAP DN indefinitely — the precise harm the feature's own comments warn about — and nothing in the chart can now fix it.
- **REMEDIATION**: append to the README section (after the "What Debug exposes" paragraph, README.md:241-243):

  ```markdown
  **Turning it off has an order.** The Job only runs while it renders, so set
  `oauthDebug.enabled=false` and run the upgrade — that run is what patches the level back —
  **before** you set `oauthDebug.manage=false`, if you set it at all. Going straight to
  `manage=false` while the cluster is at `Debug` removes the Job, the RBAC *and* the uninstall
  revert without ever patching, and the cluster stays at `Debug` until somebody puts it back by
  hand: `oc patch authentications.operator.openshift.io cluster --type=merge -p '{"spec":{"logLevel":"Normal"}}'`.
  ```

  and add to the values.yaml two-switches comment (after values.yaml:570, "…saw nothing happen."):

  ```yaml
  #
  # TURNING IT OFF HAS AN ORDER: set enabled=false and UPGRADE FIRST — that run is what patches
  # the level back — and only then, optionally, manage=false. Going straight to manage=false
  # while the cluster is at Debug removes the Job, the RBAC and the uninstall revert without
  # ever patching, and nothing this chart can render will fix it afterwards.
  ```
- **Test that would catch a regression**: not mechanically testable — this is prose about an operational sequence; the chart cannot render its way out of a flag it no longer sees (that inability is the finding).
- **Risk of the remediation**: none — comment and doc text only; no rendered output changes (verify with `helm template` diff, which must be empty).

> **Codex:** **CONFIRMED** — this is A5's defect with a stronger explanation of the missing
> pre-delete safety net. Default/`manage=false` rendering contains zero OAuth objects, so neither an
> apply nor revert actor remains. The earlier passes should explicitly require **two separate
> successful upgrades** (`enabled=false`, then `manage=false`); combining both values in one upgrade
> is still unsafe. Merge A5 and B8 into one documentation change.

### B9. "Five documents cite that line" is not the measured count — it is five pinned citations across two documents
- **Severity**: low
- **Category**: docs
- **Location**: charts/group-sync-dashboard/templates/oauth-debug-rbac.yaml:4-5; charts/group-sync-dashboard/templates/oauth-debug-job.yaml:11-12; charts/group-sync-dashboard/README.md:234-235; local-development/tests/test_chart_strategy.py:157-159 and 178
- **Claim**: the sentence "five documents cite that line (`test_docs_citations.py` pins them)" appears in four new places, but what the citation checker pins is `#NO WRITE VERB` anchors, and those number five *citations* in *two* documents. Counting loose paraphrases instead gives four documents before this feature and five only by self-including the README section the feature itself adds.
- **Trigger**: `grep -rc "#NO WRITE VERB" docs/*.md local-development/*.md charts/group-sync-dashboard/README.md`
- **Evidence**:
  ```
  docs/reference-architecture.md:4
  docs/unmanaged-audit-design.md:1        <- five citations, two documents (same at HEAD)
  ```
  Loose (case-insensitive "no write verb") at HEAD: values.yaml, reference-architecture.md, unmanaged-audit-design.md, API.md — four files, none of the mentions in values.yaml/API.md being citations of the line.
- **Cost if unfixed**: in a codebase whose test infrastructure exists because imprecise citations "were repaired by hand twice in one day", a numerically wrong claim about that very infrastructure, repeated four times, teaches readers to stop trusting the counts.
- **REMEDIATION**: reword all four sites. oauth-debug-rbac.yaml:4-5:

  ```
  # `rbac.yaml` states "NO WRITE VERB ON ANYTHING THE DASHBOARD REPORTS ON" — pinned by five
  # citations across the docs (`test_docs_citations.py`). Putting `patch` on the dashboard's
  ```
  oauth-debug-job.yaml:11-12:
  ```
  # This Job WRITES to a core platform object. The dashboard must not be able to: `rbac.yaml` states
  # "NO WRITE VERB ON ANYTHING THE DASHBOARD REPORTS ON", pinned by five citations across the docs. So the
  ```
  README.md:233-235:
  ```
  **The write does not go on the dashboard.** Patching that object is a write to a core platform
  object, and `rbac.yaml` states *"NO WRITE VERB ON ANYTHING THE DASHBOARD REPORTS ON"* — cited
  five times across the docs. So the grant lives on a ServiceAccount used only by the two hook Jobs, pinned with
  ```
  test_chart_strategy.py:157-159 (class docstring): replace "and five documents cite that line" with "pinned by five citations across the docs"; line 178: replace `"""The invariant. If this fails, five documents became false."""` with `"""The invariant. If this fails, every document citing rbac.yaml's header became false."""`
- **Test that would catch a regression**: none sensible — `test_docs_citations.py` deliberately checks that anchors resolve, not that prose counts are right ("the guarantee is narrower than 'the docs are right'", its own docstring).
- **Risk of the remediation**: comment/docstring text only; zero rendered-output and zero test-behaviour change.

> **Codex:** **CONFIRMED** — `rg -c '#NO WRITE VERB'` measured four occurrences in
> `docs/reference-architecture.md` and one in `docs/unmanaged-audit-design.md`: five citations in two
> documents. The four scoped sites saying “five documents” are false. What the prior passes missed
> beyond the raw count is that they also blurred
> “citation” and case-insensitive paraphrase; the proposed “five citations across the docs” wording is
> the accurate, stable statement.

### B10. "Unpinned it would be patch on every object in the group" overstates what the pin buys
- **Severity**: low
- **Category**: docs
- **Location**: charts/group-sync-dashboard/templates/oauth-debug-rbac.yaml:28-31; docs/reference-architecture.md:736-738; local-development/tests/test_chart_strategy.py:199-201
- **Claim**: the `resources: ["authentications"]` field already bounds the rule — unpinned, it would be patch on every *authentications* object in the group, not "every object in the group" (which holds kubeapiservers, etcds, ingresscontrollers, …). And the API has exactly one authentications object, `cluster`, so the pin is exactness insurance, not the wall the three sentences describe.
- **Trigger**: RBAC semantics — a rule authorises only the `resources` it names; confirmed indirectly by probe 8 (`patch authentications.config.openshift.io/cluster => no`, a different group being the only reason).
- **Evidence**: the rendered rule (`render-manage.yaml`):
  ```yaml
  - apiGroups: [operator.openshift.io]
    resourceNames: [cluster]
    resources: [authentications]
    verbs: [get, patch]
  ```
  Removing `resourceNames` widens this to `authentications` objects only — nothing else in `operator.openshift.io` becomes patchable.
- **Cost if unfixed**: a reviewer who knows RBAC reads an inflated justification and starts double-checking every other claim in the file; a reviewer who doesn't learns wrong RBAC semantics from a chart that is otherwise a teaching example.
- **REMEDIATION**: oauth-debug-rbac.yaml:28-33, replace the comment:

  ```yaml
    # `get` and `patch` on ONE named object. resourceNames is honoured for both — unlike `create` and
    # `list`, where a request carries its name in the body or not at all, so a name-pinned rule never
    # authorises them. Unpinned, this would be patch on every `authentications` object in the group —
    # the API has exactly one, `cluster`, so the pin costs nothing today and keeps the grant exact if
    # more ever appear.
    #
    # No `update`: --type=merge is a PATCH. No `list`, no `watch`, and no other resource.
  ```
  docs/reference-architecture.md:736-738, replace the two sentences:
  ```markdown
  Pinning `resourceNames` keeps the grant exact: unpinned, the rule would be `patch` on every
  `authentications` object in the group — today exactly one, `cluster`, which is the cluster's whole
  authentication-operator configuration. `resourceNames` IS honoured for `patch`, unlike `create` and
  `list` where the name is not in the request path.
  ```
  test_chart_strategy.py:199-201, replace the docstring:
  ```python
          """Unpinned, this would be patch on every `authentications` object in the group — today
          exactly one, `cluster`, the whole authentication-operator configuration. resourceNames IS
          honoured for `patch`, unlike `create`/`list` where the name is not in the request path."""
  ```
- **Test that would catch a regression**: none — prose accuracy.
- **Risk of the remediation**: comment-only; the rendered ClusterRole is byte-identical (comments inside `rules:` render verbatim into the manifest text but change no parsed rule — verify by re-running the class, which parses YAML precisely so comment edits cannot break it).

> **Codex:** **CONFIRMED** — the parsed rule names only the `authentications` resource. Kubernetes
> RBAC rules authorize the named API groups, resources, verbs, and optional resource names; removing
> this pin does not authorize other resources in `operator.openshift.io`
> ([RBAC documentation](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)). What the
> prior passes missed is where the meaningful defense moves: because the API currently has only the
> singleton `cluster`, B7's exact API-group/resource/rule-set test prevents real widening; this name
> pin is cheap future-proofing, not protection from today's other operator resources.

### B11. README: "with `get` and `patch` and nothing else" hides the deployments read entirely
- **Severity**: low
- **Category**: docs
- **Location**: charts/group-sync-dashboard/README.md:235-237
- **Claim**: the section describes the write SA's grant as `resourceNames: ["cluster"]`, "with `get` and `patch` and nothing else" — but the same ClusterRole's second rule grants `get` on deployments (cluster-wide today, name-pinned after F3), which the README section never mentions. A security reader concludes the SA can touch exactly one object; the live probes say otherwise.
- **Trigger**: compare README.md:235-237 against the rendered role (two rules) or probe (a)-(d) in F3.
- **Evidence**: F3's `can-i` output (`get deploy in kube-system => yes`) versus the README sentence quoted above.
- **Cost if unfixed**: the one paragraph an auditor will quote back understates the grant; the correction then reads as a discovery instead of a disclosure.
- **REMEDIATION**: replace README.md:235-239 (assumes F3's pin; if F3 is rejected, say "plus `get` on Deployments cluster-wide" instead):

  ```markdown
  five documents. So the grant lives on a ServiceAccount used only by the two hook Jobs: `get` and
  `patch` pinned with `resourceNames: ["cluster"]` to that one object, plus `get` pinned to the
  `oauth-openshift` Deployment so the Job can watch the rollout it triggered — and nothing else. The
  dashboard's own role stays read-only, and `test_chart_strategy.py` fails if that ever stops being
  true.
  ```
  (Adjust the first words to F9's rewording if both land.)
- **Test that would catch a regression**: F1 + F7's tests are what make the final sentence of the paragraph true; the prose itself is not mechanically testable.
- **Risk of the remediation**: doc text only.

> **Codex:** **CONFIRMED** — the managed render has two rules: named authentication `get/patch` and
> Deployment `get`. The current README sentence therefore understates the write identity's total
> authority. What the prior passes missed is sequencing with A7/B3: say “pinned to the named Deployment”
> only after that pin lands; until then it is Deployment `get` cluster-wide.

### B12. Ref-arch: "the chart's only write to anything outside its own namespace" collides with the auth-delegator grant
- **Severity**: low
- **Category**: docs
- **Location**: docs/reference-architecture.md:734-735
- **Claim**: with `oauthProxy.apiTokenAccess.enabled` (default false), the chart binds `system:auth-delegator`, granting `create` on tokenreviews and subjectaccessreviews — cluster-scoped creates that `rbac.yaml:110-115` itself calls "real privilege". The new absolute sentence contradicts the chart's own header comment three files away, which is the exact failure mode rbac.yaml:53-57 warns about ("an absolute claim sitting … below its own counter-example").
- **Trigger**: read the two files side by side; `rbac.yaml:99` gates the binding on `apiTokenAccess.enabled`, and values.yaml:813-815 defaults it false.
- **Evidence**: rbac.yaml:110-113: "WHAT IT GRANTS, PLAINLY: create on tokenreviews and subjectaccessreviews. … They are cluster-scoped and they are real privilege". versus reference-architecture.md:734: "That is the chart's only write to anything outside its own namespace".
- **Cost if unfixed**: whoever enables API-token access now holds a doc that is provably false, and the falseness lands in the security-review section of the reference architecture.
- **REMEDIATION**: replace reference-architecture.md:734-736 first sentence:

  ```markdown
  That is the chart's only write to a *persisted* object outside its own namespace — the optional
  delegated-auth binding (`apiTokenAccess`, default off) adds cluster-scoped `create` on
  tokenreviews/subjectaccessreviews, which validate tokens and store nothing — and it is deliberately
  not reachable by the dashboard process: the two hook Jobs that enable and revert the OAuth server's
  `spec.logLevel` are its only consumers.
  ```
- **Test that would catch a regression**: none — prose.
- **Risk of the remediation**: doc text only.

> **Codex:** **CONFIRMED** — rendering with `oauthProxy.apiTokenAccess.enabled=true` produces a
> ClusterRoleBinding to `system:auth-delegator`; the chart's own scoped comments describe that role as
> cluster-scoped `create` on TokenReview and SubjectAccessReview. Those requests validate and do not
> persist objects, but they are still write verbs, so the absolute sentence is false. The proposed
> “only persisted mutation” qualifier resolves the collision the prior architecture prose missed.

### B13. Two pre-existing "no patch anywhere" sentences are now false at `oauthDebug.manage=true` and need the qualifier
- **Severity**: low
- **Category**: docs
- **Location**: docs/reference-architecture.md:744-746; docs/unmanaged-audit-design.md:169-171
- **Claim**: ref-arch says "it holds at every setting: `helm template` … renders zero occurrences of `"patch"`", and unmanaged-audit-design says "the only write verbs anywhere in the chart are `get`/`create`/`update` on the leader-election Lease". Both were measurements of the whole chart; at `oauthDebug.manage=true` the render now contains `verbs: ["get", "patch"]`, so both universal claims have acquired an undisclosed exception — and the ref-arch sentence sits ten lines *below* the new table describing the patch grant.
- **Trigger**: `helm template … --set oauthDebug.manage=true | grep -c '"patch"'`
- **Evidence**:
  ```
  $ grep -c '"patch"' render-manage.yaml
  1
  $ grep -n '"patch"' render-manage.yaml
  212:    verbs: ["get", "patch"]
  ```
  (Zero at defaults — the five unmanagedAudit renders stay clean, so the *measurement* is intact; the *universal phrasing* is what broke.)
- **Cost if unfixed**: these are the sentences the docs deploy to prove the chart is verifiable rather than trusted; the first reader who renders with the new flag and greps finds the counter-example and downgrades the rest of the document.
- **REMEDIATION**: reference-architecture.md:744-746, replace:

  ```markdown
  This is checkable rather than asserted, and for the dashboard it holds at every setting:
  `helm template` with `config.unmanagedAudit.mode` set to `off`, `log`, `annotate`, an unrecognised
  word and empty renders zero occurrences of `"patch"` at the default `oauthDebug.manage=false` —
  and opting in adds it only to the hook Jobs' own role above, never to the dashboard's. A
  conditional `patch` on `rolebindings` and
  ```
  docs/unmanaged-audit-design.md:170-171, replace:
  ```markdown
  occurrences of `"patch"`** in each of the five renders, and — at the default
  `oauthDebug.manage=false` — the only write verbs anywhere in the chart are `get`/`create`/`update`
  on the leader-election Lease. Opting in to `oauthDebug` adds `get`/`patch` on one named
  `authentications` object, bound to the hook Jobs' own ServiceAccount and never the dashboard's;
  see the chart README's "OAuth server log level" section. Enforced by
  ```
- **Test that would catch a regression**: none for the prose; the underlying invariant is enforced by `TestNoPatchVerbAtAnyAuditMode` (defaults) plus this feature's class (opt-in), which together are what the reworded sentences describe.
- **Risk of the remediation**: doc text only. unmanaged-audit-design.md is outside the feature's file list but the brief explicitly asks whether any citing sentence became false; flagging it here for the arbiter rather than staying silent about a known-false sentence.

> **Codex:** **FIX-INADEQUATE** — renders at every unmanaged-audit mode contain zero quoted
> `"patch"` verbs by default and one when `oauthDebug.manage=true`, so the two absolute statements are
> false under the new opt-in. But the proposed remediation edits `docs/unmanaged-audit-design.md`,
> outside this review's explicit seven-file scope. Apply the qualifier to the scoped reference
> architecture now; track the out-of-scope document as a separate authorized follow-up rather than
> silently expanding this change.

### B14. The completed set-Job is orphaned by `helm uninstall`, forever, and nothing says so
- **Severity**: low
- **Category**: tech-debt
- **Location**: charts/group-sync-dashboard/templates/oauth-debug-job.yaml:37-40 (delete policy); charts/group-sync-dashboard/README.md:226-243 (section that should disclose it)
- **Claim**: hook resources are not release resources, so `helm uninstall` removes the SA/role/binding but leaves the last completed `-oauth-loglevel` Job and its pod in the namespace indefinitely (the revert Job self-deletes via `hook-succeeded`; the set Job deliberately does not). The template's "worth keeping until the next upgrade" comment is true for upgrades and silently wrong for uninstall.
- **Trigger**: `helm uninstall` of a release with `manage=true` (not executed — the cluster is shared; behaviour is Helm-documented, below).
- **Evidence**: helm.sh/docs/topics/charts_hooks/: "The resources that a hook creates are currently not tracked or managed as part of the release" and "if you create resources in a hook, you cannot rely upon `helm uninstall` to remove the resources." The Job exists on the live cluster now (`oc get jobs -n group-sync-dashboard` → `group-sync-dashboard-oauth-loglevel  Complete 1/1`), and only `before-hook-creation` — a next-run policy — applies to it.
- **Cost if unfixed**: months later someone finds an `oauth-loglevel` Job in a namespace with no release, assumes something is still managing the cluster's log level, and spends an afternoon proving a completed pod is inert.
- **REMEDIATION**: disclose rather than change behaviour (deleting on success would discard the log the comment says is the point; a TTL would contradict "until the next upgrade"). Append one sentence to the README section (after F8's added paragraph):

  ```markdown
  One artefact survives `helm uninstall` on purpose: hook resources are not release resources, so
  the last completed `-oauth-loglevel` Job (its pod holds the log of what was changed) stays in the
  namespace until the next install replaces it or somebody deletes it. It is inert — do not read it
  as a live release.
  ```
- **Test that would catch a regression**: not testable from `helm template` — it is uninstall-time Helm behaviour, not rendered output.
- **Risk of the remediation**: doc text only.

> **Codex:** **CONFIRMED** — Helm states that hook-created resources are not tracked as release
> resources and cannot be assumed to be removed by uninstall
> ([Helm hooks](https://helm.sh/docs/topics/charts_hooks/)). With only
> `before-hook-creation`, the rendered apply Job has no uninstall cleanup. What the prior passes
> missed is name scope: say
> “the next install of the same release/name,” not any install; merge this duplicate with A8.

### B15. README values table: the oauthDebug rows split the `rbac.*` block and three keys have no row
- **Severity**: low
- **Category**: docs
- **Location**: charts/group-sync-dashboard/README.md:208-214
- **Claim**: the four new rows were inserted between `rbac.bindings` (line 210) and `rbac.users` (line 215), splitting a prefix group the rest of the table keeps contiguous. And `oauthDebug.image.*`, `.backoffLimit`, `.resources` have no rows at all, in a table that documents even the main deployment's `resources` — the image default being the one value a disconnected-registry cluster must override.
- **Trigger**: read the table; `grep -n "oauthDebug" charts/group-sync-dashboard/README.md` shows rows at 211-214 with `rbac.users` at 215.
- **Evidence**: quoted table order above (`rbac.bindings` → four `oauthDebug.*` rows → `rbac.users`); `grep` of the section shows no `oauthDebug.image`, `oauthDebug.backoffLimit`, or `oauthDebug.resources` row.
- **Cost if unfixed**: the person on a mirrored/disconnected cluster — the exact audience of the image override — has to find the knob by reading values.yaml instead of the table that exists to save them that.
- **REMEDIATION**: move the four `oauthDebug.*` rows to after the `rbac.users` row, and add:

  ```markdown
  | `oauthDebug.image.*` | in-cluster `openshift/cli` imagestream | `registry.redhat.io/openshift4/ose-cli:latest` failed here with ErrImagePull — needs credentials, large, unpinned. The internal imagestream is already mirrored by the release payload; override the repository if your cluster mirrors elsewhere |
  | `oauthDebug.backoffLimit` | `2` | retries are safe: the Job exits 0 when the level already matches and the merge patch is idempotent |
  | `oauthDebug.resources` | 10m/64Mi → 200m/256Mi | |
  ```
- **Test that would catch a regression**: none — table prose.
- **Risk of the remediation**: doc text only.

> **Codex:** **CONFIRMED** — inspection found the OAuth rows between `rbac.bindings` and
> `rbac.users`, and no rows for `oauthDebug.image.*`, `backoffLimit`, or `resources`. The prior passes
> missed two precision fixes: spell out requests and limits in separate table text, and merge A4's
> `Removed`-registry caveat rather than repeating the broader claim that the internal imagestream is
> always reachable.

### B16. A revert pod that cannot run fails `helm uninstall` repeatedly, and the escape hatch is undocumented
- **Severity**: low
- **Category**: docs
- **Location**: charts/group-sync-dashboard/templates/oauth-debug-revert-job.yaml:24-27 and 44-47; charts/group-sync-dashboard/README.md:226-243
- **Claim**: the revert script forgives every `oc` failure, but pod-level failures (image unpullable, unschedulable) are beyond the script's reach: `activeDeadlineSeconds: 120` fails the Job, a failed pre-delete hook fails the uninstall, and `before-hook-creation` means every retry rebuilds the same failure. The unpullable-image case is not hypothetical — it is this feature's own measured history (`ose-cli` ErrImagePull on this cluster) — yet no doc names `helm uninstall --no-hooks` as the way out.
- **Trigger**: `revertOnUninstall: true` (the default) plus an image the node can no longer pull at uninstall time (registry migrated, imagestream pruned), then `helm uninstall`.
- **Evidence**: values.yaml:596-599 records the measured ErrImagePull for the first image choice on this very cluster; Helm hook semantics: "if the hook fails, the release will fail. This is a blocking operation" (helm.sh/docs/topics/charts_hooks/). The deadline converts a hang into a failure — the template comment (revert-job:24-26) claims only that the uninstall "must not hang", which the deadline delivers, but a repeatedly *failing* uninstall is undocumented.
- **Cost if unfixed**: an operator's uninstall fails twice, they don't know `--no-hooks` exists or that using it leaves the cluster in Debug needing the manual patch — both facts this chart knows and doesn't say.
- **REMEDIATION**: append to the README section (with F8's paragraph, they form the section's operational notes):

  ```markdown
  If the revert *pod* itself cannot run — the image no longer pullable, the pod unschedulable —
  the pre-delete hook fails the uninstall after `revertDeadlineSeconds` rather than hanging it.
  `helm uninstall --no-hooks` is the escape hatch; it skips the revert, so follow it with the
  manual patch above.
  ```
- **Test that would catch a regression**: not testable from rendered output — Helm uninstall-time semantics.
- **Risk of the remediation**: doc text only.

> **Codex:** **CONFIRMED** — Helm documents hooks as blocking and release-failing when their Job
> fails, while Kubernetes applies `activeDeadlineSeconds` to the Job regardless of whether its shell
> ever starts. Thus the script's best-effort error handling cannot rescue an unpullable or
> unschedulable pod. The prior passes missed the operational distinction: `--no-hooks` abandons the
> revert; it must always be paired with a read/conditional manual `Normal` patch, not described as a
> recovery by itself. Merge this duplicate with A4.

## Sound as built

- **Nothing renders at defaults** — `helm template` (defaults) contains zero `oauth-loglevel` strings (`grep -c` = 0); the chart touches nothing unless asked.
- **The dashboard's ClusterRole gains nothing at any oauthDebug setting** — parsed the reader role from default and `manage=true` renders: structurally identical (`reader role identical at manage=true: True`); the existing `test_the_dashboards_own_role_never_gains_the_write` also covers `manage+enabled`.
- **The invariant holds on the live cluster** — `oc auth can-i patch|get authentications.operator.openshift.io/cluster --as=system:serviceaccount:group-sync-dashboard:group-sync-dashboard` → `no` and `no`, with the feature deployed.
- **The `resourceNames` pin behaves exactly as documented** — live probes as the Job SA: `patch`/`get` on `cluster` → yes; patch another name → no; unnamed patch → no; `create` → no; `list` → no; `update` → no; `delete` → no; `patch authentications.config.openshift.io/cluster` (other group) → no. The doc's claim that `resourceNames` is honoured for `patch` and not for `create`/`list` matches the probes.
- **`helm lint` clean** at `manage=true, enabled=true` (`1 chart(s) linted, 0 chart(s) failed`), and with both remediations applied to the scratch copy.
- **Every `oauthDebug.*` key is reachable** — all 11 keys are consumed by the templates (`grep -o '\.Values\.oauthDebug\.[a-z.]*'` accounts for manage, enabled, revertOnUninstall, image×3, waitSeconds, activeDeadlineSeconds, revertDeadlineSeconds, backoffLimit, resources); no dead values, no chart values.schema.json to update.
- **README table defaults match values.yaml** — `180 / 300 / 120` for waitSeconds/activeDeadlineSeconds/revertDeadlineSeconds (values.yaml:621/625/629), and the `oc rollout status` claim in the row matches the given measurement.
- **`backoffLimit: 2` cannot double-apply** — the script exits 0 before patching when `CURRENT == WANT`, and the merge patch sets a fixed value, so a retry after a successful patch is a fast no-op (read from oauth-debug-job.yaml:67-79); retries only re-run genuine pre-patch failures.
- **Image default honestly documented** — values.yaml:590-601 states the measured ose-cli failure, why the imagestream, and that the section is OpenShift-only with no meaning on plain Kubernetes; matches the given facts, nothing re-derived.
- **CI placement claim is true** — `.github/workflows/ci.yml:84` runs `pytest tests/test_chart_strategy.py -q` by path and the new class is in that file; reproduced `30 passed` on a pristine copy with the repo venv.
- **No `resource-policy: keep` anywhere in the feature** — asserted by the existing test and confirmed in the parsed render; the pre-delete-before-resource-deletion ordering it relies on is Helm-documented.
- **`test_docs_citations.py` anchors intact** — `rbac.yaml:53` still carries the `NO WRITE VERB` anchor text all five pinned citations resolve to.
- **Revert script cannot block uninstall at the script level** — `set -uo pipefail` without `-e`, every branch reaches `exit 0` (read from oauth-debug-revert-job.yaml:44-71); only pod-level failures remain (F16, a docs gap not a code defect).
- **Not probed, by instruction**: no `helm install/upgrade/uninstall`, no patching, no logLevel changes — the hook execution paths were verified from rendered output, live RBAC probes, and Helm's documented hook semantics only.

---

# Arbiter — found while installing, toggling and redeploying on the live cluster

The reviewers had read-only access, deliberately, because the cluster is in use. These three came out
of actually running the feature and are not in either report.

### C1. Toggling the level BREAKS AUTHENTICATION for the duration of the roll, and nothing says so

- **Severity**: high
- **Category**: docs (the behaviour is inherent; the silence about it is the defect)
- **Location**: `values.yaml` `oauthDebug` block; `charts/group-sync-dashboard/README.md` OAuth
  server log level section
- **Claim**: patching `spec.logLevel` makes the authentication operator roll `deploy/oauth-openshift`.
  On a cluster with one oauth replica that is a **login outage**, not a rolling update. Nothing in the
  values comments, the README or the Job's own output warns an operator that flipping this switch
  logs people out mid-session and blocks new logins until the new pod is ready.
- **Trigger**: `helm upgrade ... --set oauthDebug.manage=true --set oauthDebug.enabled=false` on a
  cluster whose oauth Deployment has `replicas: 1` — which is what CRC and every small cluster runs.
- **Evidence**: measured during this review, one toggle:

  ```
  oc get co authentication -o jsonpath='...conditions[Available].message'
    OAuthServerDeploymentAvailable: no oauth-openshift.openshift-authentication pods available on any node.

  oc get pods -n openshift-authentication
    oauth-openshift-66444df7fc-8tjd6   1/1   Terminating   6m51s
    oauth-openshift-7d4d7cc74c-jvx44   0/1   Pending       21s
  ```

  And the dashboard, watching the same cluster, recorded the knock-on effect itself:

  ```
  crc-local  unreachable  HTTP 503 on /apis/user.openshift.io/v1/groups: service unavailable
  ```

  So the toggle was observable as a cluster-wide API blip from a second application. Node pressure
  made it worse but did not cause it: requests were at 91% CPU / 81% memory, so the replacement pod
  sat `Pending` before it could start.
- **Cost if unfixed**: somebody enables login capture during business hours on a small cluster and
  logs everyone out. The switch reads as a logging change, which is the least alarming kind.
- **REMEDIATION**: state it where the decision is made, and again where it is executed. In
  `values.yaml`, inside the `oauthDebug` block immediately after `enabled`:

  ```yaml
  # ⚠️  CHANGING THIS ROLLS THE OAUTH SERVER, AND THAT IS A LOGIN OUTAGE ON A SINGLE-REPLICA
  # CLUSTER. The authentication operator replaces deploy/oauth-openshift when logLevel changes;
  # until the new pod is Ready, `authentication` reports
  #   OAuthServerDeploymentAvailable: no oauth-openshift pods available on any node
  # and in-flight logins fail. Measured on a 1-replica CRC cluster: the replacement pod sat Pending
  # (node at 91% CPU requests) and a second application watching the same cluster recorded
  # `HTTP 503 on /apis/user.openshift.io/v1/groups` while it happened.
  #
  # Check the blast radius before you flip it, in a maintenance window if the answer is 1:
  #   oc get deploy oauth-openshift -n openshift-authentication -o jsonpath='{.spec.replicas}{"\n"}'
  #
  # This applies to turning it OFF as much as ON — both are a logLevel change.
  ```

  and, in the Job, print it at the moment of acting rather than only in a values file nobody re-reads.
  Replace the pre-patch `echo` in `oauth-debug-job.yaml`:

  ```bash
          echo "patching authentications.operator.openshift.io/cluster -> ${WANT}"
          REPLICAS=$(oc get deploy oauth-openshift -n openshift-authentication \
                       -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "?")
          if [ "$REPLICAS" = "1" ]; then
            echo "⚠️  oauth-openshift runs ONE replica: this roll is a login outage, not a rolling"
            echo "    update. New logins fail until the replacement pod is Ready."
          fi
  ```
- **Test that would catch a regression**:

  ```python
      def test_the_outage_warning_survives(self):
          """The behaviour is inherent to a logLevel change; the WARNING is the deliverable.

          A reader who does not know this reads `oauthDebug.enabled` as a logging switch and flips it
          during business hours. Measured on a 1-replica cluster: authentication reported
          "no oauth-openshift pods available on any node".
          """
          ok, out = render(**self.ON)
          assert ok, out
          assert "login outage" in out, (
              "the Job no longer warns that a single-replica roll is an outage"
          )
          values = (CHART / "values.yaml").read_text()
          assert "LOGIN OUTAGE" in values.upper(), (
              "values.yaml no longer warns at the point the decision is made"
          )
  ```
- **Risk of the remediation**: none functional — one extra read-only `oc get` and two `echo`s. The
  `deployments get` grant it needs is already present (and B3/A7 argue it should be pinned to
  `oauth-openshift`, which this read is compatible with).

> **Codex:** **CONFIRMED** — the documentation defect and single-replica login outage are real. The
> upstream operand Deployment runs `oauth-server ... --v=${LOG_LEVEL}` and uses RollingUpdate; with
> desired replicas one, the measured state shown here has zero available OAuth pods. What the prior
> passes got wrong is the blast-radius wording: existing OAuth access tokens remain valid until
> expiry or deletion, so I explicitly **refute and retract** “logs people out mid-session”
> ([OpenShift token management](https://docs.redhat.com/en/documentation/openshift_container_platform/4.21/html/authentication_and_authorization/managing-oauth-access-tokens)).
> Also, a 503 from `/apis/user.openshift.io/v1/groups` proves a contemporaneous API blip, not that
> `oauth-openshift` served that endpoint. Keep the proposed, narrower warning: new and in-flight login
> flows fail while no OAuth pod is ready. The extra Deployment read is already permitted.

### C2. The first image choice could not be pulled at all — FIXED before review, recorded for the record

- **Severity**: was high, now resolved
- **Category**: tech-debt
- **Location**: `values.yaml` `oauthDebug.image`
- **Claim**: the original default `registry.redhat.io/openshift4/ose-cli:latest` needs
  registry.redhat.io credentials, is a large image, and `:latest` is unpinned. It failed outright here.
- **Evidence**:

  ```
  Pulling image "registry.redhat.io/openshift4/ose-cli:latest"
  Failed to pull image ...: copying system image from manifest list: copying config: context canceled
  Error: ErrImagePull / ImagePullBackOff
  helm history: 75  failed  Upgrade "group-sync-dashboard" failed: context canceled
  ```

  The whole `helm upgrade` failed, so the feature did not merely degrade — it broke the release.
- **REMEDIATION**: applied. The default is now the in-cluster imagestream the release payload already
  mirrors, `image-registry.openshift-image-registry.svc:5000/openshift/cli:latest`, with the
  measurement recorded in the values comment. See **A4**, which notes a documented exception to
  "every OpenShift cluster ships this" — that qualifier still needs adding.
- **Test that would catch a regression**:

  ```python
      def test_the_image_is_not_a_credentialed_registry(self):
          """registry.redhat.io needs a pull secret this chart does not create, and the failure mode
          is a FAILED RELEASE, not a degraded feature: measured ErrImagePull -> `helm upgrade` failed
          with "context canceled"."""
          ok, out = render(**self.ON)
          assert ok, out
          assert "registry.redhat.io" not in out, (
              "the log-level Job image needs credentials the chart does not provide"
          )
  ```

> **Codex:** **CONFIRMED** — **resolved as built**. Both rendered Jobs use
> `image-registry.openshift-image-registry.svc:5000/openshift/cli:latest`, and the managed render has
> no `registry.redhat.io` reference. What the original fix missed, and A4 later supplied, is that an
> internal imagestream reference does not make the registry endpoint available when the Image
> Registry Operator is `Removed`; C2 needs no further image change, only that retained caveat.

### C3. Enabling this via `--set` on an existing release silently drops the release's other values

- **Severity**: medium
- **Category**: docs
- **Location**: `charts/group-sync-dashboard/README.md`, the new OAuth server log level section
- **Claim**: this is Helm's behaviour rather than the chart's, but this feature is the one that makes
  an operator reach for `--set` against a long-lived release, so it is where the warning belongs.
  Upgrading with only `--set oauthDebug.*` discards every other user-supplied value.
- **Trigger**: `helm upgrade <rel> <chart> --set oauthDebug.manage=true` on a release installed with
  `-f my-values.yaml` or earlier `--set`s.
- **Evidence**: done by the arbiter, on the live release, by accident:

  ```
  before:  config.unmanagedAudit.mode=log   oauthProxy.apiTokenAccess.enabled=true
  after `helm upgrade ... --set oauthDebug.manage=true --set oauthDebug.enabled=true`:
           oauthDebug only
  symptom: /api/clusters -> HTTP 403 (the oauth-proxy login page), because apiTokenAccess reverted
           to the chart default
  ```

  A second application's token access broke, and the cause was three commands earlier.
- **Cost if unfixed**: an operator enables a logging prerequisite and silently reverts unrelated
  production settings. The symptom appears elsewhere, which is the expensive kind of bug.
- **REMEDIATION**: in the README's OAuth section:

  ```markdown
  **Pass your whole value set when you enable this on an existing release.** `helm upgrade` with only
  `--set oauthDebug.*` discards every other user-supplied value and reverts it to the chart default —
  measured here: a release carrying `oauthProxy.apiTokenAccess.enabled=true` lost it, and API token
  access broke three commands later with no obvious connection. Either re-pass your values file:

      helm upgrade gsd charts/group-sync-dashboard -f my-values.yaml --set oauthDebug.manage=true

  or use `--reuse-values` deliberately. Check afterwards with
  `helm get values gsd -n group-sync-dashboard`.
  ```
- **Risk of the remediation**: none — documentation only.

> **Codex:** **FIX-INADEQUATE** — the defect is confirmed by local Helm 3.14 help: upgrade exposes
> `--reuse-values`, `--reset-values`, and `--reset-then-reuse-values`; absent reuse or a re-passed
> values file, the chart defaults are the base. The proposed example is incomplete because every
> scoped live-release command later uses namespace `group-sync-dashboard`, but the upgrade example
> omits `-n group-sync-dashboard`; it can target the wrong release/namespace or fail. Add the
> namespace to both upgrade alternatives and explain that `--reuse-values` deliberately merges the
> release's last values with new overrides
> ([Helm upgrade](https://helm.sh/docs/helm/helm_upgrade/)).

---

## Codex pass

Codex `gpt-5.6-sol` at `xhigh`: append your verdict **inline under each finding** as
`> **Codex:** …`, using one of **CONFIRMED** (and what the two prior passes missed), **REFUTED**
(with the evidence that kills it), or **FIX-INADEQUATE** (the defect is real but the proposed
remediation is wrong, incomplete, or introduces a new problem — the most valuable verdict here).

Attack in particular:

1. **A1 vs the proposed `PRE_GEN` fix.** Capturing the generation before the patch and requiring
   `gen -gt PRE_GEN` — does that actually close it, or can the operator bump the generation for an
   unrelated reason, or NOT bump it at all when the level change needs no Deployment change (leaving
   the Job to burn its whole budget)? Is the authentication CR's own
   `status.observedGeneration`/`status.generations[]` a better signal? Say which and why.
2. **B1's binding test.** Confirm the mutation really does pass 30/30 today, and that the proposed
   binding-subject test fails before and passes after. If the test can be satisfied by a mutation it
   does not catch, say so.
3. **A6/B2 overlap.** Both propose a `fail` guard for `waitSeconds >= activeDeadlineSeconds`. Are the
   two remediations compatible, and is `fail` at render time right, or does it break `helm rollback`
   / an ArgoCD diff of an existing release?
4. **The interaction between findings, and the ORDER to apply them.** Several touch the same lines of
   `oauth-debug-job.yaml` and the same test class. Give an application order that does not conflict,
   and name any pair whose fixes are mutually exclusive.
5. **Anything all three of us missed.** Add `## Codex — additional findings` at the end, in this
   document's format.

Do not re-raise anything outside the seven in-scope files.

### Codex answers

1. **Reject A1's `PRE_GEN` remediation.** It fixes the measured old-steady-state false positive,
   but it does not prove that *this* request caused or completed anything. I evaluated the proposed
   predicate against five snapshots:

   ```text
   snapshot                         current loop   PRE_GEN loop   full completion
   old steady state                    true           false            true
   unrelated generation bump           true            true            true
   old ready + new unready surge        true            true           false
   desired rollout complete             true            true            true
   desired state, no generation bump    true           false            true
   ```

   The second row is the unrelated-bump false positive the question anticipates; the fifth is the
   needless full-budget wait. The authentication CR's `status.observedGeneration` is a better
   *causal acknowledgement*: OpenShift defines it as the last CR generation the operator has “dealt
   with.” Capture the CR's `metadata.generation` after the patch and require status to reach it.
   `status.generations[]` is useful corroboration for the exact tracked Deployment, but its API
   contract says only “last generation of the workload controller”; neither field alone proves that
   ready pods serve the requested verbosity. The decision is therefore:

   - require authentication `status.observedGeneration >=` the post-patch CR generation;
   - require the `oauth-openshift` container template's `LOG_LEVEL` to be `2` for Normal or `4` for
     Debug (the upstream command consumes it as `--v=${LOG_LEVEL}`); and
   - require the full Kubernetes Deployment completion predicate, including
     `status.replicas == spec.replicas`, from one Deployment snapshot.

   That passes a true no-op immediately, cannot be satisfied by the old template after this CR
   generation is acknowledged, and does not confuse a surge's ready old pod with the desired new
   pod. The local OpenShift API source documents Normal/Debug as glog 2/4 and defines both status
   fields at
   `/Users/olasumbo/go/pkg/mod/github.com/openshift/api@v0.0.0-20231020115248-f404f2bc3524/operator/v1/types.go:98`,
   `:101`, `:112`, and `:128`; the upstream Deployment executes the environment value
   ([operator Deployment](https://github.com/openshift/cluster-authentication-operator/blob/master/bindata/oauth-openshift/deployment.yaml#L51-L56)).

2. **B1's mutation is real, and its test is necessary but insufficient.** Exact scratch results:

   ```text
   current 30 tests + binding changed to dashboard helper: 30 passed
   proposed B1 test + mutated binding:                    1 failed, 6 passed
   proposed B1 test + current binding:                    7 passed
   subject namespace changed to other-namespace:          7 passed
   ```

   The proposed test ignores `subject.namespace`. More importantly, its one default render misses a
   supported-values collision. This command rendered successfully:

   ```text
   helm template t charts/group-sync-dashboard --namespace sar-probe \
     --set ingress.host=t.example.com --set oauthDebug.manage=true \
     --set serviceAccount.create=false \
     --set serviceAccount.name=t-group-sync-dashboard-oauth-loglevel

   serviceaccounts: [t-group-sync-dashboard-oauth-loglevel]
   deployment_sa:   [t-group-sync-dashboard-oauth-loglevel]
   write_subjects:  [[ServiceAccount/t-group-sync-dashboard-oauth-loglevel, namespace=sar-probe]]
   oauth_jobs_sa:   [t-group-sync-dashboard-oauth-loglevel, t-group-sync-dashboard-oauth-loglevel]
   ```

   That is one Kubernetes identity used by the dashboard, both Jobs, and the write binding. D1 gives
   the required render guard and a test that varies `serviceAccount.name`. The subject test must also
   compare the exact `kind`, `name`, and `namespace`, and identify the binding by its exact
   `roleRef`, not only a name substring.

   Mutation breadth was worse than either report stated. Each independent M1–M7 mutation passed the
   entire present suite, **30/30**: hardcoded Debug apply payload, dashboard-SA binding, widened API
   group, added secrets rule, removed hook annotations, Debug revert payload, and misspelled wait
   target.

3. **Use one render-time guard, but narrow its promise.** A6 and B2 are the same change and must not
   both be pasted in. In a scratch chart, their `ge` guard rejected 300/300 and 400/300, allowed the
   defaults and 600/720, and left `helm lint` clean. It also allowed 299/300. Because Kubernetes
   counts the whole Job lifetime, strict `<` eliminates the deterministically impossible
   configurations but cannot guarantee that the loop's timeout branch wins the race with the Job
   deadline.

   `fail` is still the correct minimal mechanism. Put it inside `manage`, adopt an explicit headroom
   policy (the existing defaults and B2's positive case both provide 120 seconds), and change the
   prose from an absolute guarantee to: the headroom is reserved for scheduling, pull, reads and the
   patch; a pod-level failure can still reach the Job deadline first. A guarded chart cannot record
   an invalid revision. A rollback to a revision predating the guard uses that revision's stored
   manifest/hook and does not acquire a later template guard; a rollback to a guarded revision was
   valid when recorded. Helm's target-revision hook behavior is documented in
   [Helm issue 5825](https://github.com/helm/helm/issues/5825#issuecomment-569738746). An Argo CD diff
   with a currently invalid value combination will fail manifest generation; that is intentional
   validation and the error tells the operator which deadline to raise.

4. **Application order.** This order avoids tests pinning intermediate text and resolves shared
   lines once:

   1. Apply D1's ServiceAccount collision guard, then the strengthened exact binding/collision tests
      from B1. This closes the central security invariant before correctness or prose work.
   2. Apply one of A7/B3's Deployment-name pins and update the scoped reference table, then add B7's
      exact two-rule test.
   3. Rewrite the apply script once: A3's failed-read handling; D3's no-early-exit behavior; the CR
      observed-generation/direct-`LOG_LEVEL` replacement for A1 (not `PRE_GEN`); and D2's one-snapshot
      full completion predicate. Then update B4's behavioral assertions and add C1's accurate
      single-replica warning.
   4. Add one strengthened A6/B2 guard with explicit headroom and qualified docs.
   5. Add A2's `post-rollback` hook and its residual-risk documentation, then add B6's test expecting
      exactly the three hook events. Add B5's revert-payload test.
   6. Merge duplicate documentation changes rather than applying them twice: A4+B16, A5+B8,
      A8+B14, and A7+B3. Then apply B9–B12, B15, C2's retained caveat, and C3 with the namespace.
      Apply only B13's in-scope reference-architecture edit; its other document needs separate
      authorization.

   The mutually exclusive alternatives are A1's `PRE_GEN` code versus the CR/direct-template
   solution; A6 versus B2 as duplicate same-site guards; and A7 versus B3 as duplicate rule edits.
   B6's exact two-event assertion conflicts with A2 and must be rewritten for three events. A3 and D3
   are not alternatives, but their edits overlap and must be composed in one block.

5. **Three additional defects survived all three passes.** D1 is a direct bypass of the central
   ServiceAccount separation through supported values. D2 is a second independent false-positive in
   the rollout predicate. D3 makes every already-requested-but-not-yet-rolled state bypass the wait
   entirely. Full findings and fixes follow.

## Codex — additional findings

### D1. A supported ServiceAccount value gives the dashboard the supposedly unreachable write role

- **Severity**: critical
- **Category**: rbac
- **Location**: `charts/group-sync-dashboard/templates/oauth-debug-rbac.yaml:1-59`;
  `local-development/tests/test_chart_strategy.py:154-255`
- **Claim**: the Job identity is derived from the release fullname, but the dashboard's configurable
  `serviceAccount.name` is never checked against it. Setting them equal makes the dashboard and hook
  Jobs the same namespaced Kubernetes identity. The dedicated ClusterRole still looks separate, but
  its binding now grants `patch` to the dashboard itself, falsifying the feature's central invariant.
- **Trigger**:

  ```bash
  helm template t charts/group-sync-dashboard --namespace sar-probe \
    --set ingress.host=t.example.com \
    --set oauthDebug.manage=true \
    --set serviceAccount.create=false \
    --set serviceAccount.name=t-group-sync-dashboard-oauth-loglevel
  ```

- **Evidence**: parsed output from that exact command contains one ServiceAccount named
  `t-group-sync-dashboard-oauth-loglevel`; the dashboard Deployment's `serviceAccountName`, both Job
  pod specs, and the write ClusterRoleBinding subject all equal that name in `sar-probe`. With
  `serviceAccount.create=true`, the chart instead emits two manifests for the same ServiceAccount
  identity, which is also invalid. Every current test passes because none varies the dashboard SA
  name. Kubernetes defines ServiceAccounts as namespaced identities and pod `serviceAccountName` as
  the selection mechanism
  ([Kubernetes ServiceAccounts](https://kubernetes.io/docs/concepts/security/service-accounts/)).
- **Cost if unfixed**: a documented chart value can hand the long-running dashboard `get/patch` on
  `authentications.operator.openshift.io/cluster`. A compromised dashboard can then change the
  cluster authentication operand's logging state, exactly what the separate identity was designed
  to make unreachable.
- **REMEDIATION with complete code**: prepend the collision guard to
  `oauth-debug-rbac.yaml`, before its existing `manage` block:

  ```yaml
  {{- $oauthDebugServiceAccount := printf "%s-oauth-loglevel" (include "gsd.fullname" .) -}}
  {{- if and .Values.oauthDebug.manage
        (eq (include "gsd.serviceAccountName" .) $oauthDebugServiceAccount) -}}
  {{- fail (printf "serviceAccount.name must not equal %q while oauthDebug.manage=true: that name is reserved for the hook Jobs, and sharing it gives the dashboard their patch grant" $oauthDebugServiceAccount) -}}
  {{- end -}}
  {{- if .Values.oauthDebug.manage }}
  ```

  Replace only the old opening `{{- if .Values.oauthDebug.manage }}` with this block; retain its one
  existing closing `{{- end }}`.
- **Test**:

  ```python
      def test_the_write_identity_cannot_be_the_dashboard_identity(self):
          ok, out = render(**self.ON)
          assert ok, out
          docs = self._docs(out)
          job_sa = [d for d in docs if d.get("kind") == "ServiceAccount"
                    and d["metadata"]["name"].endswith("-oauth-loglevel")]
          assert len(job_sa) == 1
          job_sa = job_sa[0]["metadata"]["name"]

          deployments = [d for d in docs if d.get("kind") == "Deployment"]
          assert len(deployments) == 1
          dashboard_sa = deployments[0]["spec"]["template"]["spec"]["serviceAccountName"]
          assert dashboard_sa != job_sa

          roles = [d for d in docs if d.get("kind") == "ClusterRole"
                   and d["metadata"]["name"] == job_sa]
          bindings = [d for d in docs if d.get("kind") == "ClusterRoleBinding"
                      and d.get("roleRef", {}).get("name") == job_sa]
          assert len(roles) == len(bindings) == 1
          assert bindings[0]["roleRef"] == {
              "apiGroup": "rbac.authorization.k8s.io",
              "kind": "ClusterRole", "name": job_sa,
          }
          assert bindings[0]["subjects"] == [{
              "kind": "ServiceAccount", "name": job_sa, "namespace": "default",
          }]

          ok, out = render(**self.ON, serviceAccount__create="false",
                           serviceAccount__name=job_sa)
          assert not ok, "dashboard and write Job may not share a ServiceAccount identity"
          assert "reserved for the hook Jobs" in out
  ```

  Scratch verification: normal managed render succeeds; the collision render exits nonzero with
  the guard message; `helm lint` remains clean.
- **Risk of the remediation**: a previously accepted but security-invalid value combination stops
  rendering. No valid default or non-colliding custom ServiceAccount name changes.

### D2. The rollout predicate can accept one ready old pod plus one unready new pod

- **Severity**: high
- **Category**: correctness
- **Location**: `charts/group-sync-dashboard/templates/oauth-debug-job.yaml:94-119`
- **Claim**: the loop checks `availableReplicas >= desired` and `updatedReplicas >= desired`, but not
  total `.status.replicas == desired`. During a surge, those counts can refer to different pods: the
  old pod supplies availability while the new, updated pod exists but is not Ready. The Job then
  reports completion before the new log level is served. Five separate `oc get` calls also permit a
  cross-generation mixture that never existed in one API snapshot.
- **Trigger**: desired replicas 1, RollingUpdate with one old Ready pod and one new unready pod:
  `generation=observedGeneration`, `spec.replicas=1`, `status.replicas=2`,
  `availableReplicas=1`, `updatedReplicas=1`. The current predicate evaluates true.
- **Evidence**: the synthetic matrix in Codex answer 1 evaluates the current and `PRE_GEN` predicates
  true for that snapshot and the full completion predicate false. Kubernetes' own Deployment
  completion helper requires updated, total, and available replicas all to equal desired, with the
  observed generation caught up
  ([DeploymentComplete](https://pkg.go.dev/k8s.io/kubernetes/pkg/controller/deployment/util#DeploymentComplete)).
  The upstream OAuth Deployment is RollingUpdate
  ([operator manifest](https://github.com/openshift/cluster-authentication-operator/blob/master/bindata/oauth-openshift/deployment.yaml)).
- **Cost if unfixed**: the later login-capture consumer can begin while only the old pod is Ready and
  therefore see no Debug login line; in the Normal direction, the Job can claim PII logging stopped
  while the old Debug pod remains available.
- **REMEDIATION with complete code**: replace the existing wait initialization and loop with this
  single-snapshot, desired-template-aware completion check (used after D3's read/conditional patch):

  ```bash
          EXPECTED_V={{ if .Values.oauthDebug.enabled }}4{{ else }}2{{ end }}
          TARGET_CR_GEN=$(oc get authentications.operator.openshift.io cluster \
                            -o jsonpath='{.metadata.generation}')
          DEADLINE=$(( $(date +%s) + {{ .Values.oauthDebug.waitSeconds }} ))
          echo "waiting up to {{ .Values.oauthDebug.waitSeconds }}s for oauth-openshift at --v=${EXPECTED_V}"
          while :; do
            if [ "$(date +%s)" -ge "$DEADLINE" ]; then
              echo "⚠️  timed out waiting for the requested OAuth rollout; inspect:"
              echo "    oc get authentications.operator.openshift.io cluster -o yaml"
              echo "    oc get deploy oauth-openshift -n openshift-authentication -o yaml"
              exit 0
            fi

            CR_OBS=$(oc get authentications.operator.openshift.io cluster \
                       -o jsonpath='{.status.observedGeneration}' 2>/dev/null || echo -1)
            SNAPSHOT=$(oc get deploy oauth-openshift -n openshift-authentication \
              -o jsonpath='{.metadata.generation}{"|"}{.status.observedGeneration}{"|"}{.spec.replicas}{"|"}{.status.replicas}{"|"}{.status.availableReplicas}{"|"}{.status.updatedReplicas}{"|"}{.spec.template.spec.containers[?(@.name=="oauth-openshift")].env[?(@.name=="LOG_LEVEL")].value}' \
              2>/dev/null || true)
            IFS='|' read -r gen obs want total avail updated live_v <<< "$SNAPSHOT"

            if [ "${CR_OBS:--1}" -ge "${TARGET_CR_GEN:-0}" ] \
               && [ "$live_v" = "$EXPECTED_V" ] \
               && [ "${obs:--1}" -ge "${gen:-0}" ] \
               && [ "${updated:-0}" -eq "${want:-1}" ] \
               && [ "${total:-0}" -eq "${want:-1}" ] \
               && [ "${avail:-0}" -eq "${want:-1}" ]; then
              echo "rollout complete: generation ${gen}, ${avail}/${want} available at --v=${live_v}"
              break
            fi
            sleep 5
          done
  ```

  Before applying, verify the target OpenShift minor exposes the operand verbosity in the
  `LOG_LEVEL` env value with the read-only JSONPath used above; the upstream command consumes that
  value as `--v=${LOG_LEVEL}`. If that implementation detail differs on a supported minor, use its
  equivalent direct desired-template field rather than falling back to `PRE_GEN`.
- **Test**:

  ```python
      def test_rollout_requires_the_requested_template_and_no_old_pods(self):
          ok, out = render(**self.ON, oauthDebug__enabled="true")
          assert ok, out
          job = [d for d in self._docs(out) if d.get("kind") == "Job"
                 and d["metadata"]["name"].endswith("-oauth-loglevel")][0]
          script = job["spec"]["template"]["spec"]["containers"][0]["command"][-1]
          assert "LOG_LEVEL" in script and "EXPECTED_V=4" in script
          assert '.status.replicas}' in script
          assert '"${total:-0}" -eq "${want:-1}"' in script
          assert "IFS='|' read -r gen obs want total avail updated live_v" in script
  ```
- **Risk of the remediation**: this intentionally waits longer than the old false-positive paths.
  It relies on the operator's operand-template representation, so the read-only JSONPath must be
  checked against every supported OpenShift minor. Timeout remains non-fatal by the existing design.

### D3. `CURRENT == WANT` skips rollout verification even when the operand is still stale

- **Severity**: medium
- **Category**: correctness
- **Location**: `charts/group-sync-dashboard/templates/oauth-debug-job.yaml:65-75`
- **Claim**: the Job exits immediately when the CR already contains the requested value. CR intent
  and operand convergence are different states. A retry after a timed-out run, or an upgrade during
  the operator's reconcile window, sees `CURRENT == WANT` and never checks whether the Deployment
  template or pods have caught up.
- **Trigger**: a first Job patches Debug and times out/exits 0 while the operator is delayed; a second
  upgrade starts before the Deployment converges. Its first read returns Debug, so line 72 exits 0.
- **Evidence**: the rendered script places `exit 0` before `DEADLINE=`. A shell trace with
  `CURRENT=WANT=Debug` reaches no Deployment read at all. This is the no-op counterpart to A1's live
  timeline: the CR was already changed while the generation-27 pod did not start until 29 seconds
  after the first Job claimed completion.
- **Cost if unfixed**: retries and later upgrades are unable to repair or even observe the exact
  delayed-rollout state the wait loop exists for, leaving downstream login capture nondeterministic.
- **REMEDIATION with complete code**: replace the current read/early-exit/patch block with this block,
  then always continue into D2's wait:

  ```bash
          WANT={{ if .Values.oauthDebug.enabled }}Debug{{ else }}Normal{{ end }}
          echo "requested logLevel: ${WANT}"

          if ! CURRENT=$(oc get authentications.operator.openshift.io cluster \
                           -o jsonpath='{.spec.logLevel}'); then
            echo "ERROR: cannot read authentications.operator.openshift.io/cluster; refusing to confuse an API failure with an unset Normal level" >&2
            exit 1
          fi
          echo "current logLevel:   ${CURRENT:-<unset, i.e. Normal>}"

          if [ "${CURRENT:-Normal}" = "$WANT" ]; then
            echo "spec already requests ${WANT}; verifying the operand rollout"
          else
            echo "patching authentications.operator.openshift.io/cluster -> ${WANT}"
            oc patch authentications.operator.openshift.io cluster --type=merge \
              -p "{\"spec\":{\"logLevel\":\"${WANT}\"}}"
          fi
  ```

  This also composes A3's required failed-read behavior; do not apply A3 later as a second rewrite.
- **Test**:

  ```python
      def test_an_already_requested_level_still_verifies_the_operand(self):
          ok, out = render(**self.ON, oauthDebug__enabled="true")
          assert ok, out
          job = [d for d in self._docs(out) if d.get("kind") == "Job"
                 and d["metadata"]["name"].endswith("-oauth-loglevel")][0]
          script = job["spec"]["template"]["spec"]["containers"][0]["command"][-1]
          start = script.index('echo "spec already requests ${WANT}')
          wait = script.index("DEADLINE=")
          assert "exit 0" not in script[start:wait]
          assert "verifying the operand rollout" in script[start:wait]
  ```
- **Risk of the remediation**: an already-correct, fully converged cluster performs a few extra
  read-only calls before exiting; with D2 it completes on the first snapshot. A stale cluster now
  waits as intended.
