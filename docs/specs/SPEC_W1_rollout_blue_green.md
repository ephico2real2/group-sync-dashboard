# SPEC W1 — blue-green with Argo Rollouts, off by default: each version opens its own database, so the migration runs on green's copy before the switch; a missing controller leaves the Deployment serving; every step is a value in the release's values file (#426)

| | |
|---|---|
| Programme | Epic E (#385), restore tools and release safety: build step 9, optional. Specified and reviewed, not scheduled: the operator's "last north star" (2026-10-01) |
| Batch | W — workload strategy |
| Release | — (post-programme; not scheduled for implementation) |
| Version on release | chart 0.69.0 (chart only) |
| Version note | No application version: the change is a chart script, templates, values and docs, all outside `publish.yml`'s image paths (`.github/workflows/publish.yml#NOTE charts/** is deliberately ABSENT`), so `appVersion` and `pyproject.toml` do not move. The chart takes a MINOR because values are added (`charts/group-sync-dashboard/Chart.yaml#MAJOR and MINOR for behaviour`). The rung follows SPEC_E5's version rule (`docs/specs/SPEC_E5_offsite_on_by_default.md`, its Version note): a spec still `specified` names a chart version above `Chart.yaml` and above every other `specified` spec's claim. On origin/main `41b30524` `Chart.yaml` is 0.59.25; the index claims chart 0.59.26 (SPEC_E4, SPEC_E3, SPEC_E6), 0.60.0 (SPEC_E2, SPEC_G2, SPEC_E5), 0.60.1 (SPEC_G3), 0.60.3 and 0.60.4 (SPEC_G4), and SPEC_E5's blocks 36 to 39 and SPEC_G4's blocks 8g to 8p move other specs up to 0.60.8 and 0.61.0. The first MINOR no spec names is 0.62.0. **This spec is not scheduled for implementation** (§1): when it is, its implementing pull request re-derives this number against the index and `Chart.yaml` of that day, with blocks 11 and 16, and records the reason under these notes (`docs/specs/README.md`, "Implementation blocks") |
| Issue | [#426](https://github.com/ephico2real2/group-sync-dashboard/issues/426) |
| Status | specified |
| Source | OB1-lite's refresh of 2026-10-01 of its own draft of 2026-09-27 (`f7266dd2` on `feat/426-rollout-blue-green`, cut from `22a485c`, never on main), written from issue #426 in full (body, comments, "Decisions and corrections (2026-10-01)"), the epic #385 and the operator's rules of 2026-10-01. Every claim of the draft was re-measured: the store, chart and tests on origin/main `41b30524` (application 2.0.0, chart 0.59.25) with Helm v4.3.0 and the repository's Python 3.14 venv; Argo Rollouts' docs and source read raw at tag v1.10.0 (the current release, 2026-08-27) and diffed against v1.9.0; Red Hat OpenShift GitOps 1.22 and 1.21 documents; Helm's docs at helm-www `main`; Argo CD v3.4.3; Kubernetes v1.37.1. All fetched 2026-10-01. The lab was not touched; its facts are the issue's own measurements of 2026-10-01 (§2.5). §7's blocks were cut from a copy of `41b30524` with the design implemented, applied back to a clean copy and compared byte for byte (§4.3). No cluster, branch or GitHub setting was changed |

## How to read this spec

The plain point first. Blue-green means running the new version (green) beside the old one (blue) and moving
readers to green only when someone says so. This dashboard keeps its history in one SQLite file, which a new image
upgrades (migrates) when it opens it and an old image refuses once upgraded. So two versions must never open one
file. The design gives **each version its own copy**: green starts from blue's newest backup copy, upgrades that copy,
and blue never sees it. The switch itself is done by the Argo Rollouts controller, a cluster component this chart does
not install; without it, the chart's Deployment keeps serving exactly as today.

Every step — turn it on, promote, abort, undo, turn it off — is a value in the release's values file, rolled out by the
release's deployment pipeline (§3.4). Commands appear only in sections labelled development or troubleshooting.

§1 is the mandate and what is out of scope. §2 is the research, each finding with its source: upstream text and code
quoted with the line numbers of the raw file, this repository by `path#anchor`. §2.6 is the riskiest part, what a
Rollout does with the data claim. §2a weighs the alternatives and maps each external claim onto the code that obeys it.
§3 is the design, with its budgets. §4 is the tests, one per issue test case `T426-k`, run before and after. §5 is the
lab walk the implementing pull request runs. §6 is what an operator sees and what it costs. §7 is the whole change as
implementation blocks, applied in order:

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_W1_rollout_blue_green.md . --apply

## Orchestrator's notes

1. **Not scheduled.** The operator, 2026-10-01: #426 is *"our last north star — we won't touch it now"*, then *"you can
   spec it out"*. This spec is written to be reviewed and kept. Its blocks are exact against origin/main `41b30524`;
   when the work is scheduled, the implementing pull request re-checks every block with `apply-spec-blocks.py`,
   re-derives the version (Version note) and the compositions in note 6, and records each change here.
2. **What the refresh changed from the draft of 2026-09-27**, each from a measurement:
   - *The operator's rules of 2026-10-01* (Helm values first; Argo CD is a conduit; no CLI as the path). The draft's
     guide promoted with `oc argo rollouts promote` or Argo CD's Resume action, aborted with `oc argo rollouts abort`,
     and turned the flag off by pausing the Argo CD sync. Now: promotion is `rollout.autoPromotionEnabled: true` in the
     values file, proved in the controller's source to remove the pause (§2.2 row 6); abort and undo are the previous
     image in the values file (§2.2 row 8); turning off needs no Argo CD step (§3.4). The refusal messages name the
     value to set, not `--api-versions`. Every command moved to a "Development and troubleshooting" section.
   - *The data window* (the orchestrator's point (1) on #426; T426-14). The issue's T426-14 bounds it by the copy's
     age only. Measured, it runs to green's first poll as leader: copy age, plus the preview, plus
     `scaleDownDelaySeconds`, plus up to 45 s for the lease, because the elector does not release its Lease on stop
     (§3.5). The seed now logs the copy's age; a test holds it.
   - *A wrong sentence in the draft's `values.yaml` comment*: "renders a Rollout instead of the Deployment" contradicted
     the `workloadRef` design it shipped. Corrected (block 10).
   - *The figure* (the orchestrator's point (2); T426-15): the label "release namespace: 3–7" is now "the five lanes on
     the right run in the dashboard's namespace", the first lane is the values file and pipeline instead of "Git · Argo
     CD", and promotion and abort name their values. Rendered light and dark and looked at (§4.3).
   - *A copy named with a pod after its stamp* (SPEC_E4's `gsd-<stamp>-<pod>.db`, when it ships): the draft's
     `copy_time` read everything between `gsd-` and `.db` and would have refused such a copy with a `ValueError`. It now
     reads the stamp's fixed width (block 1; mutant M8).
   - *Two findings the draft did not have*: turning the flag off needs the controller running, because only the
     controller takes the Rollout's hash off the active Service (§2.2 row 10); and when #4681's revision-1 bug leaves the
     Deployment's pod running, that pod may hold the lease while readers reach the Rollout's pod (§3.6 row 6).
   - *Re-cut against main*: of the draft's nineteen blocks, `Chart.yaml` (0.59.2 then, 0.59.25 now) and `docs/README.md`
     (a line now follows the runbook's) no longer applied; every block is now generated from the proof tree and checked
     to occur once (§4.3).
   - *Corrected claim of the draft*: its §6 said mutant M1 (render `replicas`) also failed
     `test_off_by_default_renders_no_rollout_object`. Measured now, M1 fails only
     `test_the_deployment_still_serves_until_a_controller_makes_the_rollout_healthy` (§4.2).
3. **Promotion without a command, and the gap that remains.** Red Hat's documented promotion is the CLI plugin
   (`oc argo rollouts promote`, §2.3), which writes the Rollout's *status* (`{"status":{"pauseConditions":null}}`,
   promote.go L36): Helm renders no status, so that path cannot be a value. The values path is
   `rollout.autoPromotionEnabled`: `false` makes the controller pause, and changing it to `true` while paused makes the
   controller remove its own pause (bluegreen.go L161-L163, pause.go L154-L158). Its cost, stated in the guide: the value
   must be set back to `false` before the next image moves, or the next release is promoted as soon as green is ready.
   **Stated gap:** the values file has no switch to scale the Deployment to 0 in the #4681 revision-1 case (§3.6 row 6);
   that is a troubleshooting step. No other operation needs a command.
4. **The issue's T426-9 is kept as written**: `autoPromotionEnabled: false` by default, `scaleDownDelaySeconds: 30`,
   `scaleDownDelayRevisionLimit: 1`. `autoPromotionSeconds` (a timed preview) is not added: it is ignored while
   `autoPromotionEnabled` is `false` (bluegreen.md L102), so it would add a value that interacts with another and needs
   a refusal of its own (§2a, row F).
5. **Lab facts are the issue's, not re-measured.** The mandate names no kubeconfig for this run, so the lab was not
   read. §2.5 quotes the issue's measurements of 2026-10-01 and the draft's of 2026-09-27, each with its date.
6. **Composition with the Epic E specs not on main** (SPEC_E2, SPEC_E3, SPEC_E4, SPEC_E5, SPEC_E6 are `specified`; none
   is applied on `41b30524`). Measured from their text, with `rollout.enabled: true`:
   - SPEC_E2's recovery mode runs its script on the same pod and `/data`, and prints `GSD_DB_PATH`; with the flag on that
     path is a colour's (`/data/rs-<hash>/gsd.db`). SPEC_E3's `restore-db.sh` restores into `/data/gsd.db` (its "live
     set"), which no colour opens while the flag is on: a restore there would change nothing a reader sees. **`gsd.rolloutGuards`
     refuses `recovery.enabled: true` with `rollout.enabled: true`** ("Turn blue-green off first"), nil-safe, so it holds
     before and after `recovery` is a value on main (block 2; T426-11 `[recovery]`; note 10).
   - SPEC_E5's offsite pass reads `--pre-upgrade-source /data/pre-upgrade`; with the flag on, a migration's copy is in
     `/data/rs-<hash>/pre-upgrade/`, so that pass prints "nothing to ship". Blue's whole directory is the way back
     instead (§3.1). When E5 is on main, the guide says so in its "What changes when it is on" list.
   - SPEC_E4 names copies `gsd-<stamp>-<pod>.db` above one replica only; `rollout.enabled` refuses `replicaCount` other
     than 1, and the seed parses such names anyway (note 2).
   - SPEC_E6's card reads the directory of `GSD_DB_PATH`, so it reports the serving colour's own pre-upgrade copies.
8. **The version ladder at implementation.** Applied to `41b30524` as it stands, the blocks move `Chart.yaml` to 0.62.0,
   above SPEC_E2, SPEC_G2, SPEC_E5, SPEC_G3, SPEC_G4, SPEC_E4, SPEC_E3 and SPEC_E6's claims, and the ladder test fails
   on the first of them (§4.3). That is the rule working: W1 is scheduled last, so it is expected to be implemented
   after those specs have shipped, and its number is re-derived then (Version note). If any `specified` spec still
   claims a chart version not above W1's on that day, W1's implementing pull request moves that spec's two cells (its
   header and its index row) to the next free rung, keeping its MINOR or PATCH, as SPEC_E5's blocks 36 to 39 do. No
   such block is written now, because which specs will still be `specified` is not known.
9. **Open questions for the operator** (only these; nothing else is guessed):
   - Q1. Keep #426 in Epic E as "specified, not scheduled", or move it to its own epic? (the epic's open question 3)
   - Q2. The lab walk (§5) needs a RolloutManager from ephico2real2/openshift-gitops-helm-chart#2, still an open issue
     with no pull request (measured 2026-10-01: `gh pr list` shows only #1, merged). Unchanged since the draft.
10. **Review of 2026-10-01, OB2 (Fable 5.1, in Codex's seat), on `12128abf`; every item accepted.** C2 refuted the budget
    in two places and C4 named a risk; the fix is OB2's patch, carried into the blocks:
    - **Accepted:** the fleet gate's `fleet-gate.json` (#481) sits beside the database and no copy carries it; the seed
      now carries it (block 1, `GATE_FILE`, `other_colours`, `carry_gate`; block 17, two tests). OB1-lite added one line
      to OB2's first test, a pre-flag copy beside `/data/gsd.db`, so that the preference for the newest other colour is
      pinned (mutant M12 survived without it).
    - **Accepted:** the refusal of `recovery.enabled: true` with the flag on is a block now, nil-safe (block 2; block 18,
      the `[recovery]` case and the guide test), replacing note 6's promise.
    - **Accepted:** the guide's refusal row, its "Blue loses the lease during the preview" section and the gate sentence
      (block 13); §2.6's row, §3.3 r, §3.5's scope, §3.6 row 12.
    - **Accepted, recorded:** on PR #518's head (`98d20df0`, SPEC_E2 implemented, not merged), blocks 8, 11, 16 and 19 no
      longer check (measured, each block alone: "Old text occurs 0 times"). Note 1 already commits the implementing pull
      request to re-check every block; this is that measurement.

## 1. The mandate, and what is out of scope

**In one sentence:** a release can run the new version beside the old one and switch readers only when the release's
values file says so, without ever letting two versions write one database file.

The operator, 2026-09-27: *"adding argocd blue green using argo rollout and separate a second templates for both
deployment and services and routes with a flag or single template to address to turn on argo rollout or deployment …
My concern is the our db migrations logic works well this option."* Then: *"Group sync dashboard just consumes it"* (the
RolloutManager). On 2026-10-01: *"our last north star — we won't touch it now"* and *"you can spec it out"*: **this spec
is written and reviewed, and is not implemented now.** The same day's rules apply in full: *"supported by Helm values
file directly"*, *"Argocd is just a conduit — don't complicate it"*, and *"we are only using the cli and --set options
only for troubleshooting and development."*

**Must not change** (issue #426):

- The default install stays a `Recreate` Deployment, with the migrations exactly as today: the default render and the
  `environments/crc.yaml` render equal main's apart from the chart label and the config checksum that hashes it (§4.3).
- No path ever runs two writers on one database file (§3.7).
- #305's refusal and #301's pre-upgrade copy stay: the store is not edited.
- The dashboard ServiceAccount loses no permission: rendered RBAC, REMOVED 0 and ADDED 0 (§4.3).
- PVCs are never removed: no template creates, edits or deletes a claim; the flag adds no claim (§2.6).

**Out of scope:** a canary strategy (refused); more than one replica (refused); creating the RolloutManager (the
cluster owner's, §2.3); a preview Route (§3.3 j); any Argo CD Application, ApplicationSet, parameter, sync-wave or
action as a mechanism; a dedicated `group-sync-dashboard-dev` namespace (the issue: overkill); changes to the store.

## 2. Research, measured

### 2.1 This repository, origin/main `41b30524`

| Fact | Source |
|---|---|
| One replica is `Recreate`, and `RollingUpdate` at one replica is refused, because both pods would open `/data/gsd.db` | `charts/group-sync-dashboard/templates/deployment.yaml#strategy=RollingUpdate is unsafe at replicaCount 1` |
| The database path is `/data/gsd.db` at one replica and `/data/$(POD_NAME)/gsd.db` above one; `$(VAR)` resolves only against earlier env entries | `charts/group-sync-dashboard/templates/deployment.yaml#MUST STAY ABOVE GSD_DB_PATH` |
| The data claim's mode is `ReadWriteMany` in `values.yaml`; an empty mode derives `ReadWriteOncePod` at one replica; reporting refuses any mode but `ReadWriteMany` | `charts/group-sync-dashboard/values.yaml#accessMode: ReadWriteMany`; `charts/group-sync-dashboard/templates/_helpers.tpl#define "gsd.accessMode"`; `charts/group-sync-dashboard/templates/_helpers.tpl#reporting.enabled=true requires persistence.accessMode=ReadWriteMany` |
| A new image copies the database to `pre-upgrade/` beside the file it opens, then migrates (#301) | `local-development/gsd/store.py#_pre_upgrade_copy` (`Path(db_path).parent / PRE_UPGRADE_DIR`) |
| An older image refuses a newer database on open (#305) | `local-development/gsd/store.py#StoreSchemaTooNew`; `KNOWN_SCHEMA_VERSION` is 20 |
| A replica that is not the lease holder polls nothing: "Standby: serve reads, write nothing" | `local-development/gsd/poller.py#Standby: serve reads, write nothing` |
| Every replica flushes its readers' activity to its own store, leader or not | `local-development/gsd/api.py#Every replica runs this, leader or not` |
| Backups and report snapshots are written by `VACUUM INTO` under a `.tmp` name, renamed, named `gsd-<stamp>.db` with a fixed-width UTC stamp | `local-development/gsd/store.py#Store._vacuum_into` |
| Defaults: a snapshot every 300 s (`reporting.snapshot.intervalSeconds`), a backup every 6 h | `local-development/gsd/config.py#reporting_snapshot_interval_seconds`; `local-development/gsd/config.py#backup_interval_hours` |
| The Lease is 30 s, renewed every 10 s; `stop()` ends the loop and does **not** release the Lease; a standby re-checks leadership every 5 s | `local-development/gsd/leader.py#LeaderElector.stop`; `local-development/gsd/poller.py#STANDBY_RECHECK_SECONDS` |
| The Route names the Service; the Service and the PodDisruptionBudget select the selector labels; the ServiceMonitor selects Services by them | `charts/group-sync-dashboard/templates/service.yaml#These labels are REQUIRED by the ServiceMonitor`; `charts/group-sync-dashboard/templates/monitoring.yaml#matchLabels` |
| Readiness needs only a usable store, not a poll | `local-development/gsd/api.py#/readyz` |

### 2.2 Argo Rollouts, v1.10.0 (raw files, `curl -s <raw> \| nl -ba`, fetched 2026-10-01)

The current release is v1.10.0 (2026-08-27, `gh release list -R argoproj/argo-rollouts`). OpenShift GitOps 1.22.0 ships
it; 1.21.0 ships v1.9.0 (§2.3). Every code line cited below was diffed against v1.9.0: `rollout/pause.go`,
`rollout/templateref.go` and `rollout/scale_utils.go` are identical; `rollout/bluegreen.go` differs only in the
fast-track's first test (L114, a fast rollback in 1.10, a scale-down deadline in 1.9) and one status call 1.9 makes
in `syncRolloutStatusBlueGreen`, neither of which anything here relies on.

| # | Claim | Source (quoted) |
|---|---|---|
| 1 | Blue-green switches Service selectors | `docs/features/bluegreen.md` L7: "The rollout controller ensures proper traffic routing by injecting a unique hash of the ReplicaSet to these services' selectors." |
| 2 | The first ReplicaSet gets traffic at once | L9: "If the active service is not sending traffic to a ReplicaSet, the controller will immediately start sending traffic to the ReplicaSet." |
| 3 | At rest the preview Service points at the active ReplicaSet | L81: "a revision 1 ReplicaSet is pointed to by both the `activeService` and `previewService`." |
| 4 | Defaults | L97-L99 autoPromotionEnabled "Defaults to true"; L149 scaleDownDelaySeconds "Defaults to 30"; L152-L154 scaleDownDelayRevisionLimit "limits the number of old active ReplicaSets to keep scaled up … If omitted, all ReplicaSets will be retained" |
| 5 | `autoPromotionSeconds` needs `autoPromotionEnabled` | L102: "If the `AutoPromotionEnabled` field is set to **false**, this field would be ignored." |
| 6 | Setting `autoPromotionEnabled: true` while paused promotes | `rollout/bluegreen.go` L161-L163: `if !needsBlueGreenControllerPause(c.rollout) { c.pauseContext.RemovePauseCondition(v1alpha1.PauseReasonBlueGreenPause)`; L196-L201: the pause is needed only while `AutoPromotionEnabled` is false or `AutoPromotionSeconds > 0`; `rollout/pause.go` L154-L158: with auto-promotion enabled and `autoPromotionSeconds == 0`, `CompletedBlueGreenPause` returns true |
| 7 | The CLI's promote writes status | `pkg/kubectl-argo-rollouts/cmd/promote/promote.go` L36: `clearPauseConditionsPatch = {"status":{"pauseConditions":null}}` |
| 8 | The previous template reverts a release | `docs/generated/kubectl-argo-rollouts/kubectl-argo-rollouts_abort.md` L9-L10: "Note the 'spec.template' still represents the new rollout version. If the Rollout leaves the aborted state, it will try to go to the new version. Updating the 'spec.template' back to the previous version will fully revert the rollout."; `rollout/bluegreen.go` L124-L125: no pause when the active Service already selects the newest ReplicaSet |
| 9 | `workloadRef` and `scaleDown` | `docs/features/specification.md` L36-L42: "onsuccess": the Deployment is scaled down after the Rollout becomes healthy … "If the Rollout fails the Deployment will be scaled back up."; `docs/migrating.md` L63: "To perform an update, the change should be made to the Pod template field of the Deployment."; L116: "The Rollout won't try to manage existing Deployment Pods." |
| 10 | Only the first revision scales the Deployment down, and only through the controller | `rollout/sync.go` L1102-L1108: `if revision == 1 && c.rollout.Status.Phase == v1alpha1.RolloutPhaseHealthy && … ScaleDown == v1alpha1.ScaleDownOnSuccess { … c.scaleDeployment(&targetScale)`; `rollout/scale_utils.go` L9-L35 sets `spec.replicas` with an `Update` |
| 11 | The template comes from the Deployment's `spec.template`, never its ReplicaSet's, so a Rollout pod has no `pod-template-hash` | `rollout/templateref.go` L159-L165 (the template), L168-L175 (the selector, when the Rollout names none) |
| 12 | Deleting the Rollout clears its hash from the Services, through the controller | `rollout/controller.go` L281-L290: "Rollout is deleted, queue up the referenced Service … so that the rollouts-pod-template-hash can be cleared"; `service/service.go` L153-L155 |
| 13 | #4065 (open, updated 2026-08-01) | "Rollout Creation with workloadRef Causes Service Downtime": the documented first-ReplicaSet behaviour of row 2 |
| 14 | #4681 (open, updated 2026-04-02) | "`workloadRef.scaleDown: onsuccess` never scales down Deployment for blue-green with `postPromotionAnalysis`"; its second bug is row 10's `revision == 1` |

### 2.3 Red Hat OpenShift GitOps (fetched 2026-10-01)

| Claim | Source (quoted) |
|---|---|
| GitOps 1.22.0 ships Argo Rollouts 1.10.0, 1.21.0 ships 1.9.0, both GA; Argo Rollouts GA since 1.13 | [1.22 release notes](https://docs.redhat.com/en/documentation/red_hat_openshift_gitops/1.22/html-single/release_notes/index), Table 1.1 "GitOps and component versions" and Table 1.2 |
| A RolloutManager installs the controller | [1.22 Argo Rollouts](https://docs.redhat.com/en/documentation/red_hat_openshift_gitops/1.22/html-single/argo_rollouts/index) §1.3: "After you create a RolloutManager CR, the Red Hat OpenShift GitOps Operator installs Argo Rollouts in the same namespace." |
| The controller does the work | same, §1.2.1: "The controller reads all the rollout details and brings the cluster to the same state as described in the rollout definition." |
| One mode per cluster; cluster-scoped is the default | same: "To prevent unintended privilege escalation, Red Hat OpenShift GitOps allows only one mode of Argo Rollout installation at a time."; "Cluster-scoped mode (default): The controller oversees resources throughout all namespaces within the cluster."; a namespace-scoped instance in cluster mode fails with `InvalidRolloutManagerScope` |
| Which namespaces a cluster-scoped instance manages | same: "set the CLUSTER_SCOPED_ARGO_ROLLOUTS_NAMESPACES environment variable … If this variable is not set, the RolloutManager manages rollouts only in the namespace where it is deployed." |
| The documented promotion is the CLI | same, the canary walk-through: "you must now manually promote the rollout … `$ oc argo rollouts promote rollouts-demo -n <namespace>`" |
| The OpenShift Routes plugin is for weights | same: "With OpenShift Routes, you can configure Argo Rollouts to reduce or increase the amount of traffic"; blue-green moves a selector and needs no plugin |

### 2.4 Helm, Argo CD and Kubernetes (raw files, fetched 2026-10-01)

| Claim | Source (quoted) |
|---|---|
| A render can ask whether the cluster serves a kind | helm-www `docs/chart_template_guide/builtin_objects.md` L60-L62: "`Capabilities.APIVersions.Has $version` indicates whether a version (e.g., `batch/v1`) or resource (e.g., `apps/v1/Deployment`) is available on the cluster." |
| `lookup` sees nothing in a render without a cluster | helm-www `docs/chart_template_guide/functions_and_pipelines.mdx` L263-L264: "When no object is found, an empty value is returned."; L271-L272: "Helm is not supposed to contact the Kubernetes API Server during a `helm template\|install\|upgrade\|delete\|rollback --dry-run` operation." |
| Argo CD passes the destination's API versions to Helm by default | argo-cd v3.4.3 `docs/operator-manual/application.yaml` L100-L101: "By default, Argo CD uses the API versions of the target cluster." |
| `$(VAR)` expands only from earlier variables | kubernetes v1.37.1 `staging/src/k8s.io/api/core/v1/types.go` L2653-L2656: "Variable references $(VAR_NAME) are expanded using the previously defined environment variables in the container … If a variable cannot be resolved, the reference in the input string will be unchanged." |
| A missing label reads as empty | kubernetes v1.37.1 `pkg/fieldpath/fieldpath.go` L73: `return accessor.GetLabels()[subscript], nil` |
| A PodDisruptionBudget counts a ReplicaSet not owned by a Deployment by the ReplicaSet itself | kubernetes v1.37.1 `pkg/controller/disruption/disruption.go` L296-L301: only an RS controlled by a Deployment is skipped |

### 2.5 The lab, as recorded (not re-measured, note 5)

- 2026-10-01, the issue's refresh: `oc get rolloutmanagers.argoproj.io -A` and `oc get rollouts.argoproj.io -A`: "No
  resources found"; the `rollouts.argoproj.io` CRD exists (created 2026-09-19). PVC UIDs: `group-sync-dashboard-data`
  `f065b7a4-535c-4ef1-868c-58f5afee4953`, `group-sync-dashboard-report-artifacts`
  `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`.
- 2026-09-27, the draft: the GitOps CSV `openshift-gitops-operator.v1.21.4` sets
  `CLUSTER_SCOPED_ARGO_ROLLOUTS_NAMESPACES=openshift-gitops`; its Subscription sets no `NAMESPACE_SCOPED_ARGO_ROLLOUTS`
  (cluster-scoped mode); the data claim is `ReadWriteMany`; OLM aggregates `rollouts` create/update/patch/delete into
  `admin` and `edit`, so a namespace admin can create the Rollout.

### 2.6 The data claim under a Rollout (the riskiest interaction)

| Question | Measured answer | Rule in this design |
|---|---|---|
| Which claim do the colours mount? | the Deployment's template mounts the one data claim; the Rollout takes that template (§2.2 row 11), so every colour mounts the same claim | no claim is added, changed or removed; the flag-on render has the same two claims as main (§4.3) |
| ReadWriteOncePod | admits one pod: green could never start beside blue | refused (`gsd.rolloutGuards`) |
| ReadWriteOnce | one node: green scheduled to another node cannot attach | refused, as reporting already refuses it |
| ReadWriteMany | both colours mount it; nothing in storage stops two pods opening one file (`values.yaml`'s own comment) | the only mode allowed, and safe because no two colours share a file (next row) |
| Two ReplicaSets at once, SQLite single writer | each colour's `GSD_DB_PATH` is `/data/rs-<its template hash>/gsd.db`; the hash is one value per ReplicaSet; a Rollout pod has no `pod-template-hash` and a Deployment pod no `rollouts-pod-template-hash` (§2.2 row 11; §2.4 row 5) | one file per colour; two pods of the *same* ReplicaSet can overlap in a drain, as today (§3.7) |
| The live file under RWX on NFS | WAL fails silently on NFS (`values.yaml`) | unchanged; the seed reads copies only, never a live file |
| Leader election | the Lease name is the release's; blue holds it while serving; green is a standby that serves reads and writes only activity to its own file | required on (refused off); the lease moves to green within 45 s of blue stopping (§3.5) |
| The pre-upgrade copy (#301, SPEC_M1) | written beside the file opened, so in `/data/rs-<green>/pre-upgrade/` | green migrates only its own copy; blue's whole directory is the way back |
| The report service and its claim | a separate `Recreate` Deployment reading the newest snapshot from `/data/report`; it refuses a newer schema and accepts an older one | unchanged; the report-artifacts claim is untouched |
| The fleet gate's copy (#481, SPEC_S4f) | `fleet-gate.json` sits beside the database (`local-development/gsd/fleetstate.py#GATE_FILE`); no `VACUUM INTO` copy carries it, so a seeded colour would start without it, and a fleet Lease deleted before its first sweep would read as "nothing was kept" | the seed carries it from the newest other colour, else from beside `/data/gsd.db` (block 1, `carry_gate`; two tests) |
| Disk | each colour holds a database, its `-wal` and its pre-upgrade copies | the seed keeps its own directory and the four most recently written others (§3.3 f) |
| Recovery mode, `restore-db.sh`, offsite pre-upgrade, the KPI card (SPEC_E2, E3, E5, E6) | not on main; with the flag on they read or write `/data/gsd.db` or `/data/pre-upgrade` | re-derived when they ship (Orchestrator's notes, 6) |

## 2a. Alternatives considered

| | Option | Source | What it would cost here | Verdict |
|---|---|---|---|---|
| A | Migration: blue-green only for releases with no migration (#298 knows) | the issue's option (a) | still two writers on one file: every replica flushes activity (`local-development/gsd/api.py#Every replica runs this, leader or not`), and WAL across nodes on RWX corrupts rather than errors; the chart cannot see a migration at render time | rejected: breaks "no two writers" |
| B | Migration: green read-only until promotion, migrating at promotion | the issue's option (b) | the store has no read-only mode; a new image cannot read an unmigrated schema; the migration would run after the switch with readers on green, and blue would write to a migrated file during `scaleDownDelaySeconds` | rejected: the most code, and it moves the migration after the switch |
| C | Migration: expand/contract plus a "compatible newer schema" marker #305 accepts | the issue's option (c); [expand/contract](https://www.bytebase.com/blog/database-blue-green-deployment/) | a compatibility field per migration, a relaxed #305, a discipline on every future migration, and still two writers on one file | rejected: breaks "no two writers", and weakens #305 |
| D | **Migration: each colour its own database, seeded from the running colour's newest copy** | the issue's option (d) | an init container and a path per colour; a data window (§3.5); disk for up to five colours | **chosen**: the only option with no two writers on one file, and no change to the store |
| E | Shape: a full Rollout template, the Deployment removed | `docs/migrating.md` "Convert Deployment to Rollout" | with the flag on and no controller, Helm deletes the only serving workload and nothing creates pods for an inert Rollout: an outage; and a second copy of a 500-line pod template | rejected: not fail-safe |
| F | **Shape: `workloadRef` with `scaleDown: onsuccess`, the Deployment kept without `replicas`** | §2.2 row 9 | #4681's revision-1 limit (§3.6 row 6) | **chosen**: the only fail-safe shape |
| G | Promotion: `autoPromotionSeconds` (a timed preview that promotes unless reverted) | §2.2 row 5 | a second value interacting with `autoPromotionEnabled`, ignored when it is false, so a refusal of its own | not added (note 4); the values path is `autoPromotionEnabled` |
| H | Promotion: `prePromotionAnalysis` with an AnalysisTemplate calling green's `/readyz` | bluegreen.md L116-L121 | a second CRD (AnalysisTemplate), a Job or web metric, and RBAC for it; readiness already gates promotion | rejected: no gain over readiness, more objects |
| I | Detect the controller at render with `lookup` on RolloutManagers | §2.4 row 2 | returns empty under `helm template` and in any render without a cluster connection; needs a cluster-wide list grant; Red Hat lets the controller live in another namespace | rejected; the render checks the API (`Capabilities.APIVersions.Has`) and the shape fails safe when no controller acts |
| J | The chart creates a namespace-scoped RolloutManager | the issue's second comment, retracted in its third | refused by a cluster-scoped operator (`InvalidRolloutManagerScope`, §2.3), which the lab runs (§2.5) | rejected: a cluster prerequisite, never this chart's |
| K | A preview Route | — | an OAuth login needs the Route the ServiceAccount's redirect reference names (`charts/group-sync-dashboard/templates/route.yaml`); a second Route needs a second reference and certificate | rejected; green is checked from inside the cluster |

**Reconciliation — each external claim, and the line of this repository's code that behaves accordingly:**

- Argo Rollouts injects the hash into the Services' selectors (§2.2 row 1). The chart's Service selects only the
  selector labels (`charts/group-sync-dashboard/templates/service.yaml#selector`), and the preview Service the same
  (block 9), so the controller's added key narrows each to one colour; the Route keeps naming the Service
  (`charts/group-sync-dashboard/templates/route.yaml#name: {{ include "gsd.fullname" . }}`).
- `workloadRef` takes the Deployment's `spec.template` (§2.2 row 11). The chart renders one template, the Deployment's,
  and the Rollout carries none (block 9; `test_the_deployment_still_serves_until_a_controller_makes_the_rollout_healthy`
  asserts `"template" not in rollout["spec"]`).
- Only the controller scales the Deployment down (§2.2 row 10). The chart renders no `replicas` with the flag on
  (block 3), so neither Helm nor a GitOps sync scales it back up, and without a controller Kubernetes' default of one
  replica keeps it serving.
- A missing label reads as empty and `$(VAR)` expands from earlier entries (§2.4 rows 4–5). `gsd.colourEnv` defines both
  hash variables before `GSD_DB_PATH` (block 2), and the test asserts the order.
- `autoPromotionEnabled: true` while paused promotes (§2.2 row 6). The value reaches the Rollout as written
  (`autoPromotionEnabled: {{ .Values.rollout.autoPromotionEnabled }}`, block 9).
- The previous template reverts a release (§2.2 row 8). The image is a value
  (`charts/group-sync-dashboard/templates/_helpers.tpl#define "gsd.image"`) rendered into the Deployment's template, so
  the previous image in the values file is the previous template.
- `Capabilities.APIVersions.Has` reflects the cluster the release renders for (§2.4 rows 1, 3). `gsd.rolloutGuards`
  refuses without `argoproj.io/v1alpha1/Rollout` (block 2), the same mechanism the chart's Grafana CR already uses
  (`charts/group-sync-dashboard/templates/grafana-dashboard.yaml`).
- A new image copies then migrates the file it opens (§2.1). The seed puts green's file at `/data/rs-<hash>/gsd.db`
  (block 1), so `_pre_upgrade_copy` writes beside it and `_migrate` changes it alone.

## 3. The design

### 3.1 The migration question

The problem in one line: blue-green runs two versions at once, and this store is one SQLite file that a new image
migrates on open and an older image refuses once migrated. The answer (§2a, D): **each colour opens its own file**.
Green's init container copies blue's newest copy into green's directory and verifies it; green's dashboard then opens
it exactly as today — #301's pre-upgrade copy, then the migration — before green is ready, so before any switch. Blue
never meets the new schema, so a release never reaches #305's refusal; #305 still guards an undo whose directory was
pruned (§3.6 row 10). An abort needs no restore.

### 3.2 The chart's shape

With `rollout.enabled: true` the chart renders the Deployment (no `replicas`, the `colour-seed` init container, the
colour path), a Rollout with `workloadRef` and `scaleDown: onsuccess`, a preview Service and the seed ConfigMap. With
the flag off nothing new renders and the render equals main's apart from the chart label (§4.3).

### 3.3 The design questions

| | Question | Answer | Why, and the source |
|---|---|---|---|
| a | The values | `rollout.enabled: false`, `rollout.strategy: blueGreen`, `rollout.autoPromotionEnabled: false`, `rollout.scaleDownDelaySeconds: 30` | off: it needs a cluster prerequisite (the 0.14.0 rule, `local-development/tests/test_values_defaults.py#KEPT_OFF`); a paused preview by default (T426-9); 30 s is upstream's default |
| b | What renders with the flag on | §3.2 | §2a, F |
| c | Where the migration runs | in green, on green's own copy, when the dashboard opens it, before the switch; #301's copy to `rs-<hash>/pre-upgrade/` | `local-development/gsd/store.py#_pre_upgrade_copy`, unchanged |
| d | What blue does meanwhile | serves the Route, holds the lease, polls, writes only its own file and the copies | `local-development/gsd/poller.py#Standby: serve reads, write nothing` |
| e | How a colour gets its database | the seed's six cases (block 13, "The database, colour by colour") | `charts/group-sync-dashboard/scripts/colour_seed.py`, standard library only, like `charts/group-sync-dashboard/scripts/offsite_backup.py` |
| f | Disk | its own directory and the four most recently written others | at most four others run at once: the active colour, one old active under `scaleDownDelayRevisionLimit: 1`, a replaced preview, the Deployment's pod before the controller scales it to 0 |
| g | Promotion | `rollout.autoPromotionEnabled: true` in the values file | §2.2 row 6; note 3 |
| h | Abort | the previous image in the values file; the active Service already selects blue, green is scaled down; nothing to restore | §2.2 row 8 |
| i | Undo after promotion | the previous image in the values file; blue's ReplicaSet returns and seeds from the newest copy if its schema is one blue's file has reached, else keeps its own file | the second case equals restoring #301's copy (`docs/RUNBOOK_backup_restore.md`, section 6) without the manual step |
| j | A preview Route | none; green is checked from inside the cluster | §2a, K |
| k | The RolloutManager | never rendered; the render requires the Rollout API and names the prerequisite | §2.3; §2a, J |
| l | **Flag on, no controller** | **the Deployment keeps serving**; the Rollout is inert | §2.2 row 10; two tests |
| m | The first switch | the active Service moves to the Rollout's first pod at once; readers wait for its readiness, once | §2.2 rows 2, 13 |
| n | The report service and its CronJobs | unchanged: a separate `Recreate` Deployment reading the newest copy, blue's until green leads | it accepts an older copy |
| o | The traffic plugin | not needed | §2.3 |
| p | RBAC | the chart adds and removes no Role or binding; the controller gets its own from the GitOps operator | §4.3: 70 and 70 atoms, REMOVED 0, ADDED 0 |
| q | The preview Service's labels | not the selector labels | the ServiceMonitor selects Services by them and would scrape green twice |
| r | Refused renders | no Rollout API; `replicaCount` ≠ 1; persistence off; a mode other than `ReadWriteMany`; leader election off; a strategy other than `blueGreen`; no copy source; `recovery.enabled: true` (SPEC_E2, nil-safe) | each refusal names the value to set in the release's values file |

### 3.4 Every operation is a value

| Operation | The values file | What the controller does | Command (development and troubleshooting only) |
|---|---|---|---|
| turn on | `rollout.enabled: true` | creates the Rollout's first ReplicaSet and moves the active Service to it at once | — |
| release | the new image, `rollout.autoPromotionEnabled: false` | creates green, points the preview Service at it, pauses once green is ready | `oc argo rollouts get rollout` |
| promote | `rollout.autoPromotionEnabled: true` | removes its pause, moves the active Service to green, scales blue down after 30 s | `oc argo rollouts promote` |
| abort | the previous image | the newest ReplicaSet is blue's, already active: no pause; green is scaled down | `oc argo rollouts abort` (leaves the new image wanted) |
| undo | the previous image | blue's ReplicaSet returns as a new release; the seed picks its database | — |
| turn off | the active colour's copy into `/data/gsd.db` (runbook section 4a), then `rollout.enabled: false` | the Rollout is deleted; the controller clears its hash from the Services | — |

Argo CD, where it delivers the release, applies the rendered objects and nothing else: no Application or
ApplicationSet parameter, sync-wave, action or sync option is part of this design. A paused Rollout shows as
"Suspended" in Argo CD's health (Argo Rollouts FAQ); that is display, not a mechanism.

### 3.5 The data window, as a budget

**Budget:** per release, the history green lacks is what blue wrote between the copy green seeded from and green's
first poll as leader. Scope: one release, one namespace, `replicaCount: 1`, leader election on, **while blue holds the
lease** through the preview (when it does not, §3.6 row 12). The fleet gate's state is not in the window: the seed
carries `fleet-gate.json`, and #481's backstop covers the gate until green's first sweep writes its own (§2.6).

| Part | Bound | Source |
|---|---|---|
| copy age at seed | `reporting.snapshot.intervalSeconds` (300 s) plus one poll; `config.backup.intervalHours` (6 h) with reporting off | §2.1; the seed logs the age (block 1, T426-14) |
| preview | until the values file promotes; zero with `autoPromotionEnabled: true` | §3.4 |
| blue's scale-down delay | `rollout.scaleDownDelaySeconds` (30 s) | §2.2 row 4 |
| lease handover | ≤ 45 s: 30 s lease not released on stop, ≤ 10 s to green's next round, ≤ 5 s standby re-check | §2.1 |

What is in it: every row blue wrote after the copy (poll history, readers' activity, any record a request made). Green's
first poll records the net difference from the copy as one change per group; a change made and undone inside the window
is only in blue's directory. Nothing is deleted: blue's directory is kept until four newer colours exist (§3.3 f). With
the flag on and no controller, every restart of the Deployment's pod on a new template has the first part of the window.

### 3.6 Failure modes

| # | What happens | Effect | Seen as |
|---|---|---|---|
| 1 | Flag on, no controller | the Deployment serves; each Deployment upgrade seeds a new directory from the newest copy | no RolloutManager; the Rollout has no status |
| 2 | No copy yet, a database exists | the seed refuses; the kubelet retries the init container until the leader writes one (at most a poll plus 300 s) | `Init:CrashLoopBackOff`, `colour seed refused: a database exists … but no copy` |
| 3 | A corrupt copy | refused before it takes the name; nothing left behind | the same init status, `failed integrity_check` |
| 4 | The data window | §3.5 | the seed log's copy age |
| 5 | Green's migration fails | green never becomes ready; the Rollout does not promote; blue serves | the dashboard log, as today; abort with the previous image |
| 6 | The first revision never became healthy (#4681) | the Deployment keeps its pod beside the Rollout's; separate files; the Deployment's pod may hold the lease, so the pod readers reach does not poll | the page's last poll time stops moving; Deployment READY 1/1 while the Rollout is Healthy. **No value fixes it** (note 3): scale the Deployment to 0 once (troubleshooting) |
| 7 | Turning the flag off | the Deployment reopens `/data/gsd.db`, which lacks the history since the flag went on | the guide's "Turn it off": copy the active colour's newest copy in first |
| 8 | Turning the flag off with no controller running | the active Service keeps the Rollout's hash and selects no pod: the Route answers 503 | §2.2 row 12; the guide's troubleshooting removes the key |
| 9 | Promotion left at `true` | the next release is promoted as soon as green is ready, with no pause | the guide's "Promote" |
| 10 | An undo past a migration after blue's directory was pruned | blue seeds from green's newer copy and #305 refuses it: blue never becomes ready and green keeps serving | `StoreSchemaTooNew`; restore green's pre-upgrade copy into blue's directory (runbook section 6) |
| 11 | Clock skew between nodes larger than the gap between a colour's last write and the newest copy | a returning colour keeps its own file instead of reseeding | the seed log says which it chose |
| 12 | Blue loses the lease during a preview (a stall longer than the 30 s lease) | green takes it, polls and records into its own file; blue, still the pod readers reach, stops polling and does not take it back while green renews. Promote: nothing lost. Abort: green's polls stay in green's directory, a gap in blue's history | the page's last poll time stops moving; the guide's "Blue loses the lease during the preview" |

### 3.7 The guarantee, as a budget

**No two colours open one database file.** Budget: zero shared files, per release, across every colour the Rollout or
the Deployment runs, under `rollout.enabled: true`. Enforced by the path: each ReplicaSet's pods open
`/data/rs-<its template hash>/gsd.db` (`test_every_replicaset_opens_its_own_database_seeded_first`; mutant M7). Outside
the guarantee, stated: (1) two pods of the **same** ReplicaSet can overlap when a pod is replaced in a drain — today's
behaviour for the Deployment too, with leader election and `busy_timeout` as the mitigations; (2) the seed reads a copy,
never a live file, and the copies are written by the lease holder, which is best-effort; (3) a hand edit of the
Deployment or the Rollout bypasses the render's refusals, and a GitOps controller's self-heal reverts it.

## 4. Tests

### 4.1 One test per issue test case

| ID | Test | Fails without the change because | Before | After |
|---|---|---|---|---|
| T426-1 | `test_chart_rollout.py::test_off_by_default_renders_no_rollout_object`, and the render diff of §4.3 | regression guard: nothing renders yet | passed | passed |
| T426-2 | `::test_without_the_crd_the_render_is_refused_and_names_the_prerequisite` (also: the message names the values file, never `--api-versions` or `--set`) | `rollout.enabled` is ignored: rc 0 | FAILED | passed; FAILED under M10 |
| T426-3 | `::test_the_deployment_still_serves_until_a_controller_makes_the_rollout_healthy` | no Rollout: `KeyError` | FAILED | passed; FAILED under M1, M2 |
| T426-4 | `::test_with_no_controller_the_route_still_reaches_the_deployments_pod` | no Rollout | FAILED | passed |
| T426-5 | `::test_every_replicaset_opens_its_own_database_seeded_first` | no init container | FAILED | passed; FAILED under M7 |
| T426-6 | `::test_the_seed_reads_only_the_copies_that_are_on` | no init container | FAILED | passed |
| T426-7 | `::test_the_preview_service_selects_the_pods_and_escapes_the_servicemonitor` | no preview Service | FAILED | passed |
| T426-8 | `::test_the_configmap_carries_the_script_verbatim` | no ConfigMap | FAILED | passed |
| T426-9 | `::test_the_rollout_keeps_one_old_colour_and_waits_for_a_person_by_default` | no Rollout | FAILED | passed |
| T426-10 | `::test_the_rollout_adds_no_rbac`, and the RBAC diff of §4.3 | regression guard | passed | passed |
| T426-11 | `::test_an_unsafe_combination_is_refused[replicas\|rwop\|rwo\|no-persistence\|no-election\|canary\|no-seed-source\|recovery]`, each asserting its sentence; `::test_the_guide_names_the_recovery_refusal_and_the_lease_flip_during_the_preview` | no guard: rc 0; no guide | 9 FAILED | 9 passed; `[recovery]` FAILED under M13 |
| T426-12 | `test_colour_seed_script.py`: the ten cases of the seed's table (new colour, newest across both directories, empty volume, database without copy, restart, newer copy same schema, retry after abort, undo past a migration, corrupt copy, prune), and the fleet gate's copy carried from the newest other colour before the pre-flag one, and from beside `/data/gsd.db` the first time | no script: `FileNotFoundError` in the fixture | 12 ERROR | 12 passed; FAILED under M3, M4, M5, M6, M11, M12 |
| T426-13 | `test_values_defaults.py::test_the_only_false_defaults_are_the_stated_exceptions`, `::test_every_kept_off_boolean_has_a_reason_comment_above_it` | KEPT_OFF names keys `values.yaml` lacks | 2 FAILED | passed |
| T426-14 | `test_colour_seed_script.py::test_the_seed_log_names_the_copy_and_its_age`; the bound in `docs/BLUE_GREEN.md` "What green does not have" and §3.5 | no script | ERROR | passed; FAILED under M9 |
| T426-15 | the figure: `docs/diagrams/render.py`, light and dark, looked at | no figure on main | — | two PNGs written and read; `375 px viewport: scrollWidth 375` (§4.3) |
| T426-16 | the lab walk, §5 | no RolloutManager on the lab | — | owed to the implementing pull request |
| (research) | `test_colour_seed_script.py::test_a_copy_named_with_a_pod_after_its_stamp_still_parses` | no script | ERROR | passed; FAILED under M8 |

### 4.2 The mutations

Each on a copy of the applied tree, running `tests/test_chart_rollout.py` and `tests/test_colour_seed_script.py`
(33 tests): M1 to M10 and M12 and M13 each give `1 failed, 32 passed`, M11 `2 failed, 31 passed`, failing the test
named. M1 to M10 were measured on the first revision (29 tests, `1 failed, 28 passed` each); M11 to M13 on this one.

| | Mutation | The test that fails |
|---|---|---|
| M1 | the Deployment renders `replicas: 1` with the flag on | `test_the_deployment_still_serves_until_a_controller_makes_the_rollout_healthy` |
| M2 | `scaleDown: never` | the same |
| M3 | the seed's schema check removed | `test_an_undo_past_a_migration_keeps_its_own_file` |
| M4 | `--keep-others` default 10 | `test_prune_keeps_its_own_and_the_four_newest_other_colours` |
| M5 | `integrity_check` verdict ignored | `test_a_copy_that_fails_integrity_check_is_refused_and_leaves_nothing` |
| M6 | a database with no copy starts empty | `test_a_database_without_a_copy_is_refused_never_started_empty` |
| M7 | `GSD_DB_PATH: /data/gsd.db` for every colour | `test_every_replicaset_opens_its_own_database_seeded_first` |
| M8 | the copy's stamp read as everything between `gsd-` and `.db` (the draft's) | `test_a_copy_named_with_a_pod_after_its_stamp_still_parses` |
| M9 | the seed log drops the copy's age | `test_the_seed_log_names_the_copy_and_its_age` |
| M10 | the prerequisite refusal says "pass --api-versions" (the draft's) | `test_without_the_crd_the_render_is_refused_and_names_the_prerequisite` |
| M11 | the seed never calls `carry_gate` | both fleet-gate tests |
| M12 | `carry_gate` prefers the copy beside `/data/gsd.db` to the newest other colour's | `test_a_new_colour_carries_the_fleet_gate_copy_of_the_newest_other_colour` |
| M13 | the `recovery.enabled` refusal removed | `test_an_unsafe_combination_is_refused[recovery]` |

### 4.3 The proof

| Gate | Command | Result |
|---|---|---|
| the blocks | `apply-spec-blocks.py` on a clean `git worktree add --detach … 41b30524`, then `--apply` | `19 blocks check out across 14 files`; the applied tree equals the proof tree byte for byte (`diff -rq`, `.git` and caches excluded) |
| before | the three test files on `41b30524` with blocks 17 to 19 only | `19 failed, 7 passed, 14 errors` (first revision: `17 failed, 7 passed, 12 errors`) |
| after | the same files with every block | `40 passed` (first revision: `36 passed`) |
| the review's four checks | OB2's new tests on the first revision's applied tree, then with its fix | `4 failed, 29 passed` → `33 passed` in `test_chart_rollout.py` and `test_colour_seed_script.py` (OB2 counted the guide test apart: `3 failed, 29 passed` → `32`) |
| the hermetic suite (first revision, `12128abf`; not re-run for the review's revision) | `pytest -q -p no:cacheprovider --deselect tests/test_ui.py --deselect tests/test_live_smoke.py`, main and applied | main `41b30524`: `6467 passed, 26 skipped, 655 deselected, 5 xfailed`. Applied: `1 failed, 6499 passed, 26 skipped, 655 deselected, 5 xfailed`; the one failure is `test_specs_index.py::test_a_spec_the_changelog_has_not_begun_names_versions_the_tree_has_not_reached`, `AssertionError: ('E2', 'chart 0.60.0 (chart only)', 'Chart.yaml is already 0.62.0')`: the version ladder's signal that this spec, applied today, would jump above specs that ship first (Orchestrator's notes, 8) |
| the default render (T426-1) | `helm template group-sync-dashboard charts/group-sync-dashboard`, and with `-f environments/crc.yaml`, main against applied | 2925 and 3329 lines each; 35 and 40 lines differ, every one a `helm.sh/chart` label or the `checksum/config` that hashes the labelled ConfigMap; **0 lines** with `Chart.yaml` held at 0.59.25 |
| the flag on | `helm template … -f environments/crc.yaml --api-versions argoproj.io/v1alpha1/Rollout --set rollout.enabled=true` | rc 0; kinds as main plus one Rollout, one Service, one ConfigMap; still two PersistentVolumeClaims |
| RBAC (T426-10) | every (Role or ClusterRole, apiGroup, resource, verb) and (binding, roleRef, subject) atom, `crc.yaml` main against the flag on | 70 and 70; REMOVED 0, ADDED 0 |
| lint | `helm lint charts/group-sync-dashboard` (Helm v4.3.0), flag off and `--set rollout.enabled=true` | `1 chart(s) linted, 0 chart(s) failed` both; with the flag on lint has no Rollout API and reports the refusal as `level=INFO msg="funcMap fail"` with the values-file sentence (re-run on the review's revision: the same). `--set recovery.enabled=true` with the flag on: rc 1; alone: rc 0 |
| the figure (T426-15) | `docs/diagrams/render.py docs/diagrams/rollout-blue-green/source.html <out> rollout-blue-green` | two PNGs written (433901 and 435056 bytes), the light one read; `375 px viewport: scrollWidth 375` |
| the index | `pytest tests/test_specs_index.py tests/test_docs_citations.py` in the spec's worktree; the W1 row and header mutated to `#427` in a copy | `1802 passed, 22 skipped`, W1's 29 citations each checked, none skipped; the mutant: `1 failed, 101 passed`, `AssertionError: ('W1 is #426', '427')` |
| Markdown | `markdownlint-cli2` on the applied `docs/BLUE_GREEN.md`, `docs/README.md` and the chart `README.md` | `docs/BLUE_GREEN.md`: 0 issues; the other two: 10 findings, as on main |

## 5. On the lab (the implementing pull request)

Nothing here was run for this spec. **The walk's prerequisite is a running controller**: the lab has none (§2.5), and
ephico2real2/openshift-gitops-helm-chart#2 is where the operator's GitOps chart provides the RolloutManager. The walk is
development (the operator's standing lab permission: pause the Application's auto-sync, `helm upgrade -f`), run only
when the operator gives the lab:

1. Record the UIDs of `group-sync-dashboard-data` and `group-sync-dashboard-report-artifacts` (§2.5's values).
2. **Fail safe first:** with the prerequisite still absent, roll out `rollout.enabled: true`. Expected: the Deployment's
   pod restarts once on `/data/rs-<its hash>/gsd.db` (its `colour-seed` log names the copy and its age), the Route
   answers, the Rollout's `.status` is empty.
3. The operator applies the RolloutManager (openshift-gitops-helm-chart#2). Expected: the Rollout turns Healthy, the
   active Service carries its hash, the Deployment's `spec.replicas` becomes 0, and a second rollout of the same values
   leaves it at 0 (the chart renders no `replicas`: measured then).
4. **A release with no migration:** a new image. Read green's labels (`-L rollouts-pod-template-hash,pod-template-hash`)
   and its `GSD_DB_PATH`. Expected: green seeds, no pre-upgrade copy, the Rollout pauses, `/readyz` answers on the
   preview Service, then `rollout.autoPromotionEnabled: true` rolled out promotes it; the active Service takes green's
   hash, blue is scaled down 30 s later, green takes the lease within 45 s.
5. **A release with a migration** (a branch with one migration): green's log has `pre-upgrade copy written before
   migrating` under `/data/rs-<green>/pre-upgrade/`; blue's `rs-<blue>/gsd.db` stays at the old schema (runbook
   section 1); then promote.
6. **An abort:** a third release, then the previous image rolled out. Expected: the active Service stays on blue, green
   is scaled down, blue's database is unchanged.
7. Record the PVC UIDs again; they must be unchanged. The evidence goes under `reports/<date>_<slug>/`.

## 6. What an operator sees, and what it costs

- **Off (the default):** nothing changes; the render equals main's apart from the chart label.
- **On, no controller:** the dashboard serves from the Deployment as before, on a colour directory; every restart on a
  new template starts from the newest copy (the window's first part).
- **On, with a controller:** a release runs green beside blue, pauses for a check, and switches when the values file
  says so. An abort or an undo is the previous image; no restore after an abort.
- **Costs:** the data window (§3.5); up to five colour directories on `persistence.size`; three dashboard pods at most
  at once (blue, green, and the Deployment's pod before the first scale-down); one preview Service and one ConfigMap;
  no new permission, no new claim, no new image.

## 7. Implementation blocks

Nineteen blocks over fourteen files, in apply order: the seed script, the templates, the values, the chart's version and
README, the guide, the figure's page, the docs index, the CHANGELOG, the tests. Lines added and removed per file (the
proof tree against `41b30524`): `colour_seed.py` +186, `_helpers.tpl` +62, `deployment.yaml` +43, `rollout.yaml` +64, `values.yaml` +21, `Chart.yaml` +3 −1, the chart `README.md` +2, `docs/BLUE_GREEN.md` +335, `source.html` +253, `docs/README.md` +1, `CHANGELOG.md` +8, `test_colour_seed_script.py` +207, `test_chart_rollout.py` +155, `test_values_defaults.py` +2.

The figure's PNGs cannot be blocks. With the blocks applied, render them from the repository root and read both before
committing (development):

    local-development/.venv/bin/python docs/diagrams/render.py docs/diagrams/rollout-blue-green/source.html docs/diagrams/rollout-blue-green rollout-blue-green

#### Block 1 — charts/group-sync-dashboard/scripts/colour_seed.py: the seed script, standard library only, shipped as a ConfigMap

<!-- block: charts/group-sync-dashboard/scripts/colour_seed.py | create -->
```python
#!/usr/bin/env python3
"""Give a blue-green colour its own database before the dashboard opens it. Standard library only.

With `rollout.enabled` every ReplicaSet (a colour: blue is the running one, green the new one; the
Deployment's own ReplicaSet is a colour too) opens its OWN file, /data/rs-<its template hash>/gsd.db,
so two versions never write one SQLite file (docs/BLUE_GREEN.md). This script runs as the pod's init
container, before the dashboard starts, and decides which database the colour starts from:

  1. its own file is missing, and a copy exists       -> copy the newest copy in, verified;
  2. its own file is missing, no copy, no database    -> nothing: a new install starts empty;
  3. its own file is missing, no copy, a database     -> refuse, exit 1: the kubelet retries until the
                                                         running colour's leader has written a copy;
  4. its own file exists, and the newest copy is newer and of a schema its own file has reached
                                                      -> set its own directory aside, copy the newest in
                                                         (the same release tried again after an abort,
                                                         or an undo with no migration: the newer
                                                         history wins);
  5. its own file exists, otherwise                   -> keep it (a restart of the running colour, or an
                                                         undo past a migration its image cannot read).

"A copy" is a `gsd-<UTC stamp>.db` the running colour's leader wrote with VACUUM INTO: the report
snapshot (/data/report, every reporting.snapshot.intervalSeconds) or the on-volume backup
(config.backup.dir). Newest by name across both: the stamp is UTC with microseconds, fixed width, and
leads the name. The seed log names the copy and its age, which is where the history green lacks begins.

The copy is verified before it takes the database's name: PRAGMA integrity_check on the copied bytes.
The dashboard then opens it exactly as it opens any database: an older schema is copied to pre-upgrade/
and migrated (#301), a newer one is refused (#305).

Last, it prunes: colour directories other than its own beyond the newest --keep-others, by the last
write to their database. At most four other colours run at once (the active one, one old active in
scaleDownDelaySeconds, a replaced preview, the Deployment's pod before it is scaled to 0), so the default
of 4 never removes a running one.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

PATTERN = "gsd-*.db"
COLOUR_PREFIX = "rs-"
# The fleet gate's copy kept beside the database (gsd/fleetstate.py#GATE_FILE, #481): no VACUUM INTO copy
# carries it, so a colour takes the newest other colour's, else the one beside /data/gsd.db before the flag.
GATE_FILE = "fleet-gate.json"
# The stamp's fixed width, 20260927T101500.123456Z: a copy whose name carries more after it (a pod's
# name, above one replica) still parses.
STAMP_WIDTH = 23


class SeedError(Exception):
    """A start this script refuses. Exits 1 with the reason; the kubelet retries the init container."""


def copy_time(path: Path) -> float:
    """The UTC instant in a copy's name, gsd-20260927T101500.123456Z.db, as epoch seconds."""
    stamp = path.name[len("gsd-"):len("gsd-") + STAMP_WIDTH]
    return datetime.strptime(stamp, "%Y%m%dT%H%M%S.%fZ").replace(tzinfo=UTC).timestamp()


def newest_copy(sources: list[Path]) -> Path | None:
    copies = [p for s in sources if s.is_dir() for p in s.glob(PATTERN) if p.is_file()]
    return max(copies, key=lambda p: p.name, default=None)


def schema(path: Path, *, immutable: bool) -> int:
    """PRAGMA user_version. A copy never changes, so it is read immutable; a live file is read read-only."""
    mode = "immutable=1&mode=ro" if immutable else "mode=ro"
    conn = sqlite3.connect(f"file:{path}?{mode}", uri=True)
    try:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])
    finally:
        conn.close()


def last_write(directory: Path) -> float:
    """When the colour last wrote: WAL mode commits to -wal first, so both files count."""
    times = [p.stat().st_mtime for p in (directory / "gsd.db", directory / "gsd.db-wal") if p.exists()]
    return max(times, default=directory.stat().st_mtime)


def seed(copy: Path, db: Path) -> None:
    """Copy `copy` to `db` through a temporary name, verified and synced before it takes the name."""
    tmp = db.with_name(db.name + ".seed")
    shutil.copyfile(copy, tmp)
    with tmp.open("rb") as fh:
        os.fsync(fh.fileno())
    conn = sqlite3.connect(f"file:{tmp}?immutable=1&mode=ro", uri=True)
    try:
        verdict = conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        conn.close()
    if verdict != "ok":
        tmp.unlink(missing_ok=True)
        raise SeedError(f"the copy of {copy} failed integrity_check: {verdict!r}")
    os.replace(tmp, db)
    fd = os.open(db.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    age = max(0.0, time.time() - copy_time(copy))
    # The data window's first half (docs/BLUE_GREEN.md, "What green does not have"): what the running
    # colour recorded after this copy stays in that colour's directory.
    print(f"seeded {db} from {copy} ({db.stat().st_size} bytes, schema {schema(db, immutable=True)}); "
          f"the copy was written {age:.0f} s ago")


def other_colours(data: Path, own: Path) -> list[Path]:
    """Every colour directory but this one, the most recently written first."""
    return sorted((d for d in data.glob(COLOUR_PREFIX + "*") if d.is_dir() and d != own),
                  key=last_write, reverse=True)


def carry_gate(data: Path, own: Path) -> None:
    """Put the fleet gate's copy beside this colour's database when it has none: the newest other colour's, else
    the pre-flag one beside /data/gsd.db. Without it a Lease deleted before this colour's first sweep reads as
    "nothing was kept", and a password its gate held back may be sent once more (SPEC_S4f)."""
    target = own / GATE_FILE
    if target.exists():
        return
    for source in [*(d / GATE_FILE for d in other_colours(data, own)), data / GATE_FILE]:
        if source.is_file():
            tmp = target.with_name(target.name + ".seed")
            shutil.copyfile(source, tmp)
            os.replace(tmp, target)
            print(f"carried {source} to {target}: the fleet gate's copy beside the database (#481)")
            return


def prune(data: Path, own: Path, keep_others: int) -> None:
    others = other_colours(data, own)
    for stale in others[keep_others:]:
        shutil.rmtree(stale)
        print(f"removed {stale}: older than the newest {keep_others} other colours")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", required=True, type=Path, help="this colour's database, /data/rs-<hash>/gsd.db")
    parser.add_argument("--from", dest="sources", action="append", default=[], type=Path,
                        help="a directory of gsd-<stamp>.db copies; repeat for each")
    parser.add_argument("--keep-others", type=int, default=4)
    args = parser.parse_args(argv)
    own, data = args.db.parent, args.db.parent.parent
    try:
        copy = newest_copy(args.sources)
        if args.db.exists():
            if copy is None or copy_time(copy) <= last_write(own):
                print(f"kept {args.db}: no copy is newer than this colour's last write")
            elif schema(copy, immutable=True) > schema(args.db, immutable=False):
                print(f"kept {args.db}: the newest copy {copy.name} is schema {schema(copy, immutable=True)}, "
                      f"newer than this file's; the history written since {time.ctime(last_write(own))} "
                      f"stays in that copy and its colour's directory")
            else:
                aside = own.with_name(f"{own.name}.set-aside-{int(time.time())}")
                own.rename(aside)
                print(f"set {own} aside as {aside}: {copy.name} is newer and readable")
                own.mkdir()
                seed(copy, args.db)
        elif copy is not None:
            own.mkdir(parents=True, exist_ok=True)
            seed(copy, args.db)
        elif any(p.is_file() for p in [data / "gsd.db", *data.glob("*/gsd.db")]):
            raise SeedError(f"a database exists under {data} but no copy under "
                            f"{', '.join(map(str, args.sources))} yet; the running colour's leader writes one "
                            f"on its next poll, and this init container is retried until then")
        else:
            print(f"no database under {data}: a new install, {args.db} starts empty")
        if args.db.exists():
            carry_gate(data, own)
        prune(data, own, args.keep_others)
    except (SeedError, sqlite3.Error, OSError, ValueError) as exc:
        print(f"colour seed refused: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

#### Block 2 — charts/group-sync-dashboard/templates/_helpers.tpl: the switch, the seed sources, the colour path and the refusals

<!-- block: charts/group-sync-dashboard/templates/_helpers.tpl | edit -->
```yaml
{{- end -}}

{{- define "gsd.reportName" -}}
{{- printf "%s-report" (include "gsd.fullname" .) | trunc 63 | trimSuffix "-" -}}
```

```yaml
{{- end -}}

{{- /* rollout.enabled (docs/BLUE_GREEN.md), read the way reportingEnabled is: only the literal true turns it on. */ -}}
{{- define "gsd.rolloutEnabled" -}}
{{- if eq (toString ((.Values.rollout | default dict).enabled)) "true" -}}true{{- else -}}false{{- end -}}
{{- end -}}

{{- /* The directories a new colour seeds from, space-separated: copies the running colour's leader writes on the
data claim. Empty when neither is on, which rolloutGuards refuses. */ -}}
{{- define "gsd.seedSources" -}}
{{- $dirs := list -}}
{{- if eq (include "gsd.reportingEnabled" .) "true" -}}{{- $dirs = append $dirs "/data/report" -}}{{- end -}}
{{- if and .Values.config.backup.enabled (hasPrefix "/data/" (toString .Values.config.backup.dir)) -}}
{{- $dirs = append $dirs .Values.config.backup.dir -}}
{{- end -}}
{{- join " " $dirs -}}
{{- end -}}

{{- /* One database per ReplicaSet: a Rollout's pods carry rollouts-pod-template-hash, the Deployment's
pod-template-hash, and a missing label reads as empty, so exactly one names the directory. */ -}}
{{- define "gsd.colourEnv" -}}
- name: ROLLOUTS_POD_TEMPLATE_HASH
  valueFrom:
    fieldRef:
      fieldPath: metadata.labels['rollouts-pod-template-hash']
- name: POD_TEMPLATE_HASH
  valueFrom:
    fieldRef:
      fieldPath: metadata.labels['pod-template-hash']
- name: GSD_DB_PATH
  value: /data/rs-$(ROLLOUTS_POD_TEMPLATE_HASH)$(POD_TEMPLATE_HASH)/gsd.db
{{- end -}}

{{- /* The combinations under which two colours could share a database, or a colour could not start. Each
refusal names the value to set in the release's values file, the only path a release takes (docs/BLUE_GREEN.md). */ -}}
{{- define "gsd.rolloutGuards" -}}
{{- if eq (include "gsd.rolloutEnabled" .) "true" -}}
{{- if not (.Capabilities.APIVersions.Has "argoproj.io/v1alpha1/Rollout") -}}
{{- fail "rollout.enabled: true needs the Argo Rollouts API (argoproj.io/v1alpha1 Rollout), and the cluster this release renders for does not serve it. Its controller is a cluster prerequisite this chart never creates: one RolloutManager from the cluster's OpenShift GitOps installation, provided by the cluster owner (docs/BLUE_GREEN.md, \"Before you start\"). Until it exists, set rollout.enabled: false in this release's values file and roll it out through the release's deployment pipeline." -}}
{{- end -}}
{{- if ne (toString .Values.rollout.strategy) "blueGreen" -}}
{{- fail (printf "rollout.strategy must be blueGreen; got %q. A canary would send some readers to each version, and each version keeps its own history. Set rollout.strategy: blueGreen in this release's values file." (toString .Values.rollout.strategy)) -}}
{{- end -}}
{{- if ne (int .Values.replicaCount) 1 -}}
{{- fail "rollout.enabled: true requires replicaCount: 1. Blue-green already runs a second pod during a release, and above one replica every pod keeps its own history (templates/deployment.yaml, PER-POD database file). Set replicaCount: 1 in this release's values file." -}}
{{- end -}}
{{- if not .Values.persistence.enabled -}}
{{- fail "rollout.enabled: true requires persistence.enabled: true: green seeds its database from a copy on the data claim, and an emptyDir has none. Set persistence.enabled: true in this release's values file." -}}
{{- end -}}
{{- if ne (include "gsd.accessMode" .) "ReadWriteMany" -}}
{{- fail (printf "rollout.enabled: true requires persistence.accessMode: ReadWriteMany; got %s. Blue and green run at once on one claim: ReadWriteOncePod admits one pod, and ReadWriteOnce leaves green unable to attach the claim on another node. An existing claim's mode cannot change in place (docs/RUNBOOK_backup_restore.md section 5)." (include "gsd.accessMode" .)) -}}
{{- end -}}
{{- if not .Values.leaderElection.enabled -}}
{{- fail "rollout.enabled: true requires leaderElection.enabled: true: blue and green run at once, and only the lease holder may poll and write the copies a new colour starts from. Set leaderElection.enabled: true in this release's values file." -}}
{{- end -}}
{{- if eq (toString ((.Values.recovery | default dict).enabled)) "true" -}}
{{- fail "rollout.enabled: true cannot run with recovery.enabled: true: recovery mode is one pod holding the data volume with the app stopped, and a Rollout would start it as a preview colour beside the serving one, never ready and never promoted, so nothing stops. Turn blue-green off first (docs/BLUE_GREEN.md, \"Turn it off\"), then set recovery.enabled: true in this release's values file." -}}
{{- end -}}
{{- if not (include "gsd.seedSources" .) -}}
{{- fail "rollout.enabled: true needs a copy for green to start from: set reporting.enabled: true (a snapshot every reporting.snapshot.intervalSeconds) or config.backup.enabled: true with config.backup.dir under /data/ in this release's values file." -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "gsd.reportName" -}}
{{- printf "%s-report" (include "gsd.fullname" .) | trunc 63 | trimSuffix "-" -}}
```

#### Block 3 — charts/group-sync-dashboard/templates/deployment.yaml: no `replicas` when the flag is on

<!-- block: charts/group-sync-dashboard/templates/deployment.yaml | edit -->
```yaml
  labels: {{- include "gsd.labels" . | nindent 4 }}
spec:
  replicas: {{ .Values.replicaCount }}
  strategy:
    {{- /*
```

```yaml
  labels: {{- include "gsd.labels" . | nindent 4 }}
spec:
  {{- if eq (include "gsd.rolloutEnabled" .) "true" }}
  # No replicas: the Rollout controller scales this Deployment to 0 once the Rollout is healthy; without one it serves on.
  {{- else }}
  replicas: {{ .Values.replicaCount }}
  {{- end }}
  strategy:
    {{- /*
```

#### Block 4 — charts/group-sync-dashboard/templates/deployment.yaml: the seed script's checksum on the pod

<!-- block: charts/group-sync-dashboard/templates/deployment.yaml | edit -->
```yaml
        # because the running process read it at startup.
        checksum/config: {{ include (print $.Template.BasePath "/configmap.yaml") . | sha256sum }}
        {{- with .Values.podAnnotations }}{{- toYaml . | nindent 8 }}{{- end }}
    spec:
```

```yaml
        # because the running process read it at startup.
        checksum/config: {{ include (print $.Template.BasePath "/configmap.yaml") . | sha256sum }}
        {{- if eq (include "gsd.rolloutEnabled" .) "true" }}
        checksum/colour-seed: {{ .Files.Get "scripts/colour_seed.py" | sha256sum }}
        {{- end }}
        {{- with .Values.podAnnotations }}{{- toYaml . | nindent 8 }}{{- end }}
    spec:
```

#### Block 5 — charts/group-sync-dashboard/templates/deployment.yaml: the `colour-seed` init container

<!-- block: charts/group-sync-dashboard/templates/deployment.yaml | edit -->
```yaml
      {{- with .Values.priorityClassName }}
      priorityClassName: {{ . | quote }}
      {{- end }}
      containers:
```

```yaml
      {{- with .Values.priorityClassName }}
      priorityClassName: {{ . | quote }}
      {{- end }}
      {{- if eq (include "gsd.rolloutEnabled" .) "true" }}
      # Before the dashboard opens it: this colour's own database, seeded from the running colour's newest copy.
      initContainers:
        - name: colour-seed
          image: {{ include "gsd.image" . }}
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          command:
            - python3.14
            - /scripts/colour_seed.py
            - --db
            - $(GSD_DB_PATH)
            {{- range splitList " " (include "gsd.seedSources" .) }}
            - --from
            - {{ . }}
            {{- end }}
          env: {{- include "gsd.colourEnv" . | nindent 12 }}
          securityContext: {{- toYaml .Values.securityContext | nindent 12 }}
          volumeMounts:
            - name: data
              mountPath: /data
            - name: tmp
              mountPath: /tmp
            - name: colour-seed
              mountPath: /scripts
              readOnly: true
          resources: {{- toYaml .Values.resources | nindent 12 }}
      {{- end }}
      containers:
```

#### Block 6 — charts/group-sync-dashboard/templates/deployment.yaml: the colour's database path, opened

<!-- block: charts/group-sync-dashboard/templates/deployment.yaml | edit -->
```yaml
                fieldRef:
                  fieldPath: metadata.name
            - name: GSD_DB_PATH
              {{- if gt (int .Values.replicaCount) 1 }}
```

```yaml
                fieldRef:
                  fieldPath: metadata.name
            {{- if eq (include "gsd.rolloutEnabled" .) "true" }}
            {{- include "gsd.colourEnv" . | nindent 12 }}
            {{- else }}
            - name: GSD_DB_PATH
              {{- if gt (int .Values.replicaCount) 1 }}
```

#### Block 7 — charts/group-sync-dashboard/templates/deployment.yaml: the colour's database path, closed

<!-- block: charts/group-sync-dashboard/templates/deployment.yaml | edit -->
```yaml
              value: /data/gsd.db
              {{- end }}
            # Through the helper, not the raw value: an unrecognised level does not degrade to a
            # default, it raises inside the uvicorn factory and the container never starts. The
```

```yaml
              value: /data/gsd.db
              {{- end }}
            {{- end }}
            # Through the helper, not the raw value: an unrecognised level does not degrade to a
            # default, it raises inside the uvicorn factory and the container never starts. The
```

#### Block 8 — charts/group-sync-dashboard/templates/deployment.yaml: the seed script's volume

<!-- block: charts/group-sync-dashboard/templates/deployment.yaml | edit -->
```yaml
          configMap:
            name: {{ include "gsd.fullname" . }}-curlrc
        {{- if .Values.trustedCA.injected.enabled }}
        - name: trusted-ca-injected
```

```yaml
          configMap:
            name: {{ include "gsd.fullname" . }}-curlrc
        {{- if eq (include "gsd.rolloutEnabled" .) "true" }}
        - name: colour-seed
          configMap:
            name: {{ include "gsd.fullname" . }}-colour-seed
        {{- end }}
        {{- if .Values.trustedCA.injected.enabled }}
        - name: trusted-ca-injected
```

#### Block 9 — charts/group-sync-dashboard/templates/rollout.yaml: the Rollout, the preview Service and the seed ConfigMap

<!-- block: charts/group-sync-dashboard/templates/rollout.yaml | create -->
```yaml
{{- include "gsd.rolloutGuards" . }}
{{- if eq (include "gsd.rolloutEnabled" .) "true" }}
# Blue-green with Argo Rollouts (docs/BLUE_GREEN.md). The Rollout takes its pods from the Deployment (workloadRef),
# so the pod template has one source, and only the controller scales the Deployment down, once the Rollout is
# healthy: a cluster with the CRD but no running controller leaves this object inert and the Deployment serving.
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: {{ include "gsd.fullname" . }}
  namespace: {{ .Release.Namespace }}
  labels: {{- include "gsd.labels" . | nindent 4 }}
spec:
  replicas: 1
  selector:
    matchLabels: {{- include "gsd.selectorLabels" . | nindent 6 }}
  workloadRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {{ include "gsd.fullname" . }}
    # Scaled to 0 only after the Rollout is healthy; no postPromotionAnalysis, which keeps it from ever firing (#4681).
    scaleDown: onsuccess
  strategy:
    blueGreen:
      # The Service the Route points at; the controller moves its selector to green at promotion.
      activeService: {{ include "gsd.fullname" . }}
      previewService: {{ include "gsd.fullname" . }}-preview
      # false: green waits on the preview Service until the values file sets true (docs/BLUE_GREEN.md, "Promote").
      autoPromotionEnabled: {{ .Values.rollout.autoPromotionEnabled }}
      scaleDownDelaySeconds: {{ int .Values.rollout.scaleDownDelaySeconds }}
      # One old colour in its scale-down delay at most, so colour_seed.py's --keep-others 4 never prunes a running one.
      scaleDownDelayRevisionLimit: 1
---
# Green before promotion; the running colour at rest. No Route reaches it: an OAuth login needs the Route the
# ServiceAccount's redirect reference names, so green is checked from inside the cluster (docs/BLUE_GREEN.md).
apiVersion: v1
kind: Service
metadata:
  name: {{ include "gsd.fullname" . }}-preview
  namespace: {{ .Release.Namespace }}
  # Not gsd.labels: the ServiceMonitor selects Services by the selector labels and would scrape green twice.
  labels:
    helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
    app.kubernetes.io/name: {{ include "gsd.name" . }}-preview
    app.kubernetes.io/instance: {{ .Release.Name }}
    app.kubernetes.io/managed-by: {{ .Release.Service }}
spec:
  type: ClusterIP
  selector: {{- include "gsd.selectorLabels" . | nindent 4 }}
  ports:
    - name: http
      port: {{ .Values.service.port }}
      targetPort: {{ ternary "oauth-proxy" "http" .Values.oauthProxy.enabled }}
---
# The seed script, verbatim from scripts/colour_seed.py. A test holds the two identical.
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "gsd.fullname" . }}-colour-seed
  namespace: {{ .Release.Namespace }}
  labels: {{- include "gsd.labels" . | nindent 4 }}
data:
  colour_seed.py: |
{{ .Files.Get "scripts/colour_seed.py" | indent 4 }}
{{- end }}
```

#### Block 10 — charts/group-sync-dashboard/values.yaml: the `rollout` values and their comment

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->
```yaml
# override.
strategy: ""

resources:
```

```yaml
# override.
strategy: ""

# Blue-green with Argo Rollouts (docs/BLUE_GREEN.md). OFF by default: it needs the cluster's Argo Rollouts
# controller, which a RolloutManager from the cluster's OpenShift GitOps installation provides; this chart
# never creates one. On, the Deployment stays (without `replicas`) and a Rollout takes its pod template from it
# (workloadRef, scaleDown: onsuccess), so with no controller running the Deployment keeps serving. Each version
# (a colour) opens its OWN database, /data/rs-<its template hash>/gsd.db, seeded from the running colour's
# newest copy (charts/group-sync-dashboard/scripts/colour_seed.py): green migrates its own copy before the
# switch and blue never meets a newer schema. Refused with replicaCount other than 1, a claim other than
# ReadWriteMany, persistence or leaderElection off, a strategy other than blueGreen, or no copy to seed from
# (reporting and config.backup both off). Every switch here is set in this release's values file and rolled
# out through the release's deployment pipeline.
rollout:
  enabled: false
  # blueGreen is the only strategy: canary would send some requests to each colour's own history.
  strategy: blueGreen
  # false (the default): the Rollout pauses with green on the preview Service until this release's values
  # file sets true, which promotes it (docs/BLUE_GREEN.md, "Promote"). true: green is promoted as soon as it
  # is ready, with no pause.
  autoPromotionEnabled: false
  # How long blue keeps running after the switch; Argo Rollouts' default, for the Service change to propagate.
  scaleDownDelaySeconds: 30

resources:
```

#### Block 11 — charts/group-sync-dashboard/Chart.yaml: the chart's MINOR and its history line

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->
```yaml
# CHART 0.59.25 (2026-09-30), PATCH: RUNBOOK section 1 says the card's connection row and tls chip
# are the last poll's, not Refresh's (Epic D composition review, K5).
version: 0.59.25
# 0.8.0 (2026-09-03). A Users tab — every user with a synced membership, filtered as you type on
# id or display name — and a Find member box on the group page. /users rows gain `full_name`,
```

```yaml
# CHART 0.59.25 (2026-09-30), PATCH: RUNBOOK section 1 says the card's connection row and tls chip
# are the last poll's, not Refresh's (Epic D composition review, K5).
# CHART 0.62.0 (2026-10-01), MINOR: rollout.enabled, blue-green with Argo Rollouts (#426, SPEC_W1), off by
# default; each version opens its own database, and with no Rollouts controller the Deployment keeps serving.
version: 0.62.0
# 0.8.0 (2026-09-03). A Users tab — every user with a synced membership, filtered as you type on
# id or display name — and a Find member box on the group page. /users rows gain `full_name`,
```

#### Block 12 — charts/group-sync-dashboard/README.md: the values rows

<!-- block: charts/group-sync-dashboard/README.md | edit -->
```markdown
| `strategy` | `""` | derived: `Recreate` at one replica, `RollingUpdate` above. Set explicitly to override |
| `leaderElection.enabled` | `true` | only the lease holder polls. **Best-effort, not a write fence** — see [Leader election](#leader-election). Must be `false` above one replica; the chart refuses to render otherwise |
| `leaderElection.leaseName` | `group-sync-dashboard` | the `coordination.k8s.io` Lease object's name, in the release namespace. Two releases in one namespace must not share it |
| `podDisruptionBudget.enabled` | `true` | on one replica this governs **drains**, not availability — see below |
```

```markdown
| `strategy` | `""` | derived: `Recreate` at one replica, `RollingUpdate` above. Set explicitly to override |
| `leaderElection.enabled` | `true` | only the lease holder polls. **Best-effort, not a write fence** — see [Leader election](#leader-election). Must be `false` above one replica; the chart refuses to render otherwise |
| `rollout.enabled` | `false` | blue-green with Argo Rollouts; needs the cluster's Rollouts controller, which this chart never creates. Each version opens its own database, so the migration runs on green's copy before the switch. With no controller the Deployment keeps serving. See [docs/BLUE_GREEN.md](../../docs/BLUE_GREEN.md) |
| `rollout.autoPromotionEnabled` / `.scaleDownDelaySeconds` | `false` / `30` | `false`: green waits on the preview Service; setting `true` in the release's values file promotes it. Blue keeps running this long after the switch |
| `leaderElection.leaseName` | `group-sync-dashboard` | the `coordination.k8s.io` Lease object's name, in the release namespace. Two releases in one namespace must not share it |
| `podDisruptionBudget.enabled` | `true` | on one replica this governs **drains**, not availability — see below |
```

#### Block 13 — docs/BLUE_GREEN.md: the operator's guide

<!-- block: docs/BLUE_GREEN.md | create -->
```markdown
# Blue-green releases with Argo Rollouts

This page is for the person who turns blue-green on, promotes a release, aborts one, or turns it off again.
The switch is `rollout.enabled` in the chart. It is **off by default**, and off the chart installs exactly
what it installed before.

**Every step on this page is a value in the release's values file**, rolled out through the release's
deployment pipeline. Commands appear only in the last section, "Development and troubleshooting".

**The rule behind it:** blue and green never open the same database file. Each version has its own copy.
Green starts from blue's newest copy and upgrades that copy before any reader reaches green. Blue keeps
serving on its own file the whole time.

## The short version

1. The release's values file gets a new image. The deployment pipeline rolls it out.
2. The Argo Rollouts controller starts green beside blue. Blue keeps serving.
3. Green copies blue's newest database copy into its own directory, then upgrades it (the migration).
4. The Rollout pauses. Green is checked through the preview Service.
5. The values file sets `rollout.autoPromotionEnabled: true`, and the pipeline rolls it out. The active
   Service moves to green. The Route does not change.
6. Blue stops 30 seconds later. Its directory stays on the volume, for an undo.

To abort at step 4 instead, put the previous image back in the values file. Green stops and blue carries on
untouched. There is nothing to restore.

## Words used on this page

| Word | Meaning here |
|---|---|
| blue | the version serving readers now |
| green | the new version, started beside blue |
| colour | one version's pods: one ReplicaSet of the Rollout (or of the Deployment) |
| Rollout | the Argo Rollouts object that runs blue and green; the chart renders it when `rollout.enabled` is true |
| controller | the Argo Rollouts controller: the process that acts on Rollouts; a Rollout without it does nothing |
| active Service | the Service the Route sends readers to (`<release>`); the controller points it at one colour |
| preview Service | a second Service (`<release>-preview`) the controller points at green before the switch |
| promotion | the switch: the controller moves the active Service from blue to green |
| abort | stop a release before promotion: green is scaled down and the active Service stays on blue |
| undo | go back to blue after promotion, by putting the previous image back in the values file |
| copy | a `gsd-<time>.db` file the running colour's leader writes: the report snapshot or the backup |
| migration | the schema upgrade a new image runs on the database it opens (`gsd/store.py#_migrate`) |
| RolloutManager | the OpenShift GitOps object that installs the Argo Rollouts controller; one per cluster |

## The picture

<!-- markdownlint-disable MD033 -->
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="diagrams/rollout-blue-green/rollout-blue-green.dark.png">
  <source media="(prefers-color-scheme: light)" srcset="diagrams/rollout-blue-green/rollout-blue-green.light.png">
  <img alt="Green copies blue's newest database copy into its own directory and migrates it while blue serves; promotion from the values file moves the active Service to green; an abort leaves blue untouched; with no controller the Deployment keeps serving" src="diagrams/rollout-blue-green/rollout-blue-green.light.png">
</picture>
<!-- markdownlint-enable MD033 -->

*Figure 1. Seven lanes, time flowing down. The first lane is the release's values file and its deployment
pipeline; the second is the cluster's Argo Rollouts controller, outside the dashboard's namespace; the other
five are in the dashboard's namespace. The migration runs in green, on green's own copy, before the switch;
blue never meets the new schema. An abort (red) leaves blue as it was. An undo (grey) brings blue back on the
newest copy it can read, or on its own file. The dashed box is a cluster prerequisite, not part of this chart;
everything else drawn ships with `rollout.enabled`.*

````text
VALUES FILE      CONTROLLER          ROUTE/SERVICES     BLUE                GREEN                DATA /data           REPORT
+ PIPELINE       [prerequisite]      Route->active      serves, leader  --writes--> rs-blue/gsd.db   reads newest copy
                 absent? Rollout     active->blue       polls                        report/ 5 min <--
                 inert, Deployment   preview->blue                                   backup/ 6 h
                 serves  [red]
new image  --->  sees template                                                                     report Deployment
rolled out       creates green  ---> preview->green                     1 colour-seed <--newest copy-- rolls at once,
(Deployment                                                               to rs-green/            reads blue's copy
template)                                               meanwhile blue: 2 #301 copy, migrate
                                                        serves, writes    green's copy --> rs-green/
                                                        rs-blue/ only   3 ready, no lease
                 paused: green is
                 checked; previous image back in the values file
                                  --abort [red]-------------------------> green scaled down;
                   |                                                      blue never migrated
autoPromotion -> promote -------> active->green     30 s later blue    green serves, lease, --> copies --> reads green's
Enabled: true                     Route unchanged   scaled to 0,       writes copies
                                                    rs-blue/ kept
undo: previous image --[grey]-----------------------> blue returns on the newest copy it can read, else its own rs-blue/
````

## Before you start: the controller

A Rollout is only a description. **The Argo Rollouts controller does the work**: it creates green, switches the
Services and scales blue down. Red Hat: *"The controller reads all the rollout details and brings the cluster to the
same state as described in the rollout definition."* Without it, nothing happens.

The controller is a cluster prerequisite. **This chart never creates it.** The cluster's OpenShift GitOps
installation provides one RolloutManager, which the cluster owner declares in the cluster's own GitOps
configuration (for example the operator's `openshift-gitops` chart, ephico2real2/openshift-gitops-helm-chart#2). It
is shared by every team's Rollouts on the cluster. This is Red Hat's minimal RolloutManager:

````yaml
apiVersion: argoproj.io/v1alpha1
kind: RolloutManager
metadata:
  name: argo-rollout
  namespace: openshift-gitops
spec: {}
````

Red Hat allows one mode per cluster: cluster-scoped (the default) or namespace-scoped. A cluster-scoped
RolloutManager lives in a namespace the GitOps operator's `CLUSTER_SCOPED_ARGO_ROLLOUTS_NAMESPACES` setting lists
(on the reference cluster, `openshift-gitops`). A cluster running the namespace-scoped mode
(`NAMESPACE_SCOPED_ARGO_ROLLOUTS=true` on the operator) needs a namespace-scoped RolloutManager in the release
namespace instead. Either is the cluster owner's choice; this chart creates neither.

## Turn it on

In the release's values file:

````yaml
rollout:
  enabled: true
````

Roll it out through the release's deployment pipeline. The chart refuses to render, with the reason, when:

| Setting | Why it is refused |
|---|---|
| the cluster does not serve `argoproj.io/v1alpha1` Rollout | the Rollout kind does not exist there (with the kind and no controller, see "When there is no controller") |
| `replicaCount` is not 1 | each extra replica keeps its own history already |
| `persistence.enabled: false` | green seeds from a copy on the data claim |
| `persistence.accessMode` is not `ReadWriteMany` | blue and green run at once; `ReadWriteOncePod` admits one pod, `ReadWriteOnce` one node |
| `leaderElection.enabled: false` | only the lease holder may poll and write copies |
| `rollout.strategy` is not `blueGreen` | a canary would split readers across two histories |
| `reporting.enabled` and `config.backup.enabled` both off | green has no copy to start from |
| `recovery.enabled: true` | recovery mode is one pod holding the volume with the app stopped; a Rollout would start it as a preview colour that is never ready, and nothing stops. Turn blue-green off first |

What changes when it is on:

- The Deployment stays, with the same pod template and no `replicas` field. The Rollout reads its template from
  it (`workloadRef`) and scales it to 0 once the Rollout is healthy.
- Each colour's database is `/data/rs-<hash>/gsd.db`, where `<hash>` is its ReplicaSet's template hash. An init
  container, `colour-seed`, prepares it before the dashboard starts. The pre-upgrade copy of a migration lands
  beside it, in `/data/rs-<hash>/pre-upgrade/`.
- A preview Service, `<release>-preview`, and a ConfigMap holding the seed script.

**The first switch.** The first time the controller sees the Rollout, it points the active Service at the
Rollout's first pod straight away (Argo Rollouts, "BlueGreen"). Readers wait until that pod is ready, once.
That pod starts from the newest copy, so the history since that copy is in the Deployment's directory only (see
"What green does not have"). After that every release is a blue-green release.

## A release, step by step

1. Put the new image in the release's values file, with `rollout.autoPromotionEnabled: false` (the default). The
   pipeline rolls out the Deployment's new template. The Deployment has 0 pods, so nothing starts from it; the
   controller sees the change and creates green.
2. The report service and its CronJobs are a separate Deployment. They roll at once, and read blue's copies until
   green takes over: an older copy is accepted, a newer one refused.
3. Green's `colour-seed` log names the copy it used and its age, for example `seeded /data/rs-<hash>/gsd.db from
   /data/report/gsd-….db (…); the copy was written 142 s ago`. The dashboard's log then shows the pre-upgrade copy
   and each migration.
4. The Rollout pauses with green ready on the preview Service.

If the values file carried `rollout.autoPromotionEnabled: true` instead, step 4 does not pause: green is promoted
as soon as it is ready.

## Check green before promoting

The preview Service has no Route: a browser login needs the Route the ServiceAccount's OAuth redirect names. Green
is checked from inside the cluster:

- the OpenShift console shows green's pod, its `colour-seed` log and its readiness;
- a check in the deployment pipeline calls the preview Service at
  `https://<release>-preview.<namespace>.svc:<service.port>/readyz` (`service.port` is 8080 by default).

## Promote

Set `rollout.autoPromotionEnabled: true` in the release's values file and roll it out. The controller removes its
pause as soon as it sees the value (Argo Rollouts `rollout/bluegreen.go`, `needsBlueGreenControllerPause`), and the
active Service moves to green. Blue stops after `rollout.scaleDownDelaySeconds` (30). Green takes the lease within
45 seconds after that, then polls and writes the copies the report service reads.

Before the next release, set it back to `false`, in a change rolled out before the image moves, so the next green
waits for a person again. Left at `true`, the next release is promoted as soon as green is ready: still on its own
database copy, but with no pause to check it.

## Abort

Put the previous image back in the release's values file and roll it out. The Deployment's template is then blue's
again, the Rollout's newest ReplicaSet is the one the active Service already selects, and the controller scales
green down. **Nothing to restore**: blue never saw green's schema. Green's directory stays on the volume until the
prune removes it.

Rolling the new image out again later starts green afresh: it seeds from blue's newest copy, not from its aborted
one.

## Undo after the switch

Put the previous image back in the release's values file and roll it out. Blue starts again as the new green, and
its `colour-seed` decides its database:

| Case | Blue starts on |
|---|---|
| no migration between blue and green | the newest copy: green's history is kept |
| green migrated the schema | blue's own file, as it was when blue stopped; the history since stays in green's directory |

The second row is what a restore of the pre-upgrade copy gives today (`docs/RUNBOOK_backup_restore.md`, section 6),
done for you. If blue's directory was already pruned (four newer colours ago), blue can only start from green's
newer copy, which it refuses (`StoreSchemaTooNew`); green keeps serving. Restore green's pre-upgrade copy into blue's
directory with the runbook's section 6.

## What green does not have: the data window

Green starts from a copy, not from blue's live file, so it lacks what blue recorded after that copy. The window
runs from the copy to green's first poll as leader:

| Part | How long, at most | Where it comes from |
|---|---|---|
| the copy's age when green seeds | `reporting.snapshot.intervalSeconds` (300 s) plus one poll; `config.backup.intervalHours` (6 h) with reporting off | the leader writes a copy after a poll; the seed log prints the age |
| the preview | until the values file promotes; none with `rollout.autoPromotionEnabled: true` | the person, or the pipeline |
| blue's scale-down delay | `rollout.scaleDownDelaySeconds` (30 s) | the Rollout |
| the lease moving to green | 45 s: the 30 s lease blue does not release when it stops, green's next 10 s round, the poller's 5 s re-check | `gsd/leader.py#LeaderElector.stop`, `gsd/poller.py#STANDBY_RECHECK_SECONDS` |

What blue wrote in that window — the poll history, the readers' activity, any record a request made — stays in
blue's directory. Green's first poll records how each group differs from the copy as one change, so a change made
and undone inside the window is only in blue's directory. Nothing is deleted: blue's directory is kept until four
newer colours exist. Promote soon after the check to keep the window short.

The same holds, with no preview, every time the Deployment's own pod restarts on a new template while the flag is
on and no controller runs: the new pod is a new colour.

## Blue loses the lease during the preview

Blue renews its Lease every 10 seconds and the Lease lasts 30 seconds. If blue stalls for longer than that during a
preview (a long garbage collection, a node under pressure, a partition), green's elector takes the Lease: green polls
and records into **its own** file, and blue, still the pod readers reach, stops polling. Blue does not take the
Lease back while green renews it, so the page's last poll time stops moving until the release ends:

- **promote**: green serves with the history it recorded; nothing is lost;
- **abort**: green is scaled down, its Lease expires 30 seconds later and blue takes it within 45 seconds
  (`gsd/leader.py#LeaderElector.stop`, `gsd/poller.py#STANDBY_RECHECK_SECONDS`); the polls green recorded while
  it led stay in green's directory, a gap in blue's history for the time green led.

This is why the chart refuses leader election above one replica (`templates/deployment.yaml`, "pods that lose the
lease stop polling but KEEP SERVING reads from their own database"): blue-green runs that shape on purpose, for the
length of a preview only. Keep previews short; the seed and the dashboard log say which pod led.

## When there is no controller

With the flag on and no controller, the Rollout is inert. **The Deployment keeps serving**, because only the
controller scales it down. The dashboard pod belongs to the Deployment, and its database is `/data/rs-<the
Deployment's hash>/gsd.db`. Each Deployment upgrade then starts from the newest copy, like a new colour (see the data
window above). Once the cluster owner installs the controller, the next rollout starts the Rollout.

## The Deployment still has a pod after the Rollout is healthy

The controller scales the Deployment to 0 only when the Rollout's **first** revision becomes healthy (Argo Rollouts
issue #4681). If that first revision failed and a later one succeeded, the Deployment's pod keeps running beside the
Rollout's. They never share a database, but the Deployment's pod may hold the lease, and then the pod readers reach
does not poll: the page's last poll time stops moving. **The values file has no switch for this**: the chart renders
the Deployment without `replicas` on purpose, so that the controller alone scales it. Scaling the Deployment to 0 once
is a troubleshooting step (below); the chart then leaves it at 0.

## Turn it off

With the flag off, the Deployment opens `/data/gsd.db` again, the file it had before the flag went on. That file
does not have the history recorded since. While the flag is on no pod opens `/data/gsd.db`, so:

1. Copy the active colour's newest copy (`/data/report/gsd-….db` or `/data/backup/gsd-….db`) into
   `/data/gsd.db` with `docs/RUNBOOK_backup_restore.md` section 4a; no pod needs to stop first.
2. Set `rollout.enabled: false` in the release's values file and roll it out, **while the controller still runs**.
   The Rollout is deleted, its pods stop, and the controller takes its hash off the active Service, so the Service
   selects the Deployment's pod again.

## The database, colour by colour

The seed script is `charts/group-sync-dashboard/scripts/colour_seed.py`. It runs before the dashboard, once per pod:

| This colour's file | The newest copy | What it does |
|---|---|---|
| missing | exists | copies it in, checks `integrity_check`, then renames it into place |
| missing | none, and the volume has no database | nothing: a new install starts empty |
| missing | none, but a database exists | refuses; the kubelet retries until the leader writes a copy |
| exists | not newer than the file | keeps the file (a restart) |
| exists | newer, of a schema the file has reached | sets the directory aside, copies the newest in |
| exists | newer, of a newer schema | keeps the file (an undo past a migration) |

Before that it carries the fleet gate's copy, `fleet-gate.json` (`gsd/fleetstate.py#FileBackstop`, #481), from the
newest other colour, or from beside `/data/gsd.db` the first time, because no database copy carries it: without
it a Lease deleted before this colour's first sweep would read as "nothing was kept".

Then it keeps its own directory and the four most recently written others, and removes the rest. Disk: up to five
colour directories, each about the database's size with its pre-upgrade copies, on `persistence.size`.

## Development and troubleshooting

Commands for a lab, a developer's render, or a stuck release. None of them is how a release is run.

Is the controller there?

````sh
oc get rolloutmanagers.argoproj.io -A          # one, Phase Available
oc get customresourcedefinitions.apiextensions.k8s.io rollouts.argoproj.io
oc get rollouts.argoproj.io -n <namespace> <release> -o jsonpath='{.status}'   # empty: no controller acts on it
````

Render without a cluster: `helm template` sees no cluster API, so the chart refuses `rollout.enabled: true` unless
the API is named:

````sh
helm template <release> charts/group-sync-dashboard -f <values file> --api-versions argoproj.io/v1alpha1/Rollout
````

Watch a release and reach green from a laptop:

````sh
oc argo rollouts get rollout <release> -n <namespace> --watch
oc logs -n <namespace> <green pod> -c colour-seed
oc port-forward -n <namespace> service/<release>-preview 8443:8080
curl -sk https://localhost:8443/readyz
curl -sk -H "Authorization: Bearer $(oc whoami -t)" https://localhost:8443/api/version
````

The plugin's `oc argo rollouts promote <release>` and `oc argo rollouts abort <release>` act on the Rollout's status
directly. They are for a lab: an abort by command leaves the new image in the values file, and the Rollout tries it
again as soon as it leaves the aborted state.

The Deployment's pod left running beside a healthy Rollout (above):

````sh
oc get deployments.apps -n <namespace> <release>      # READY 1/1 while the Rollout is Healthy
oc scale deployments.apps -n <namespace> <release> --replicas=0
````

The flag was turned off while no controller ran, and the Route answers 503: the active Service still carries the
Rollout's hash and selects no pod.

````sh
oc get service -n <namespace> <release> -o jsonpath='{.spec.selector}'
oc patch service -n <namespace> <release> --type json -p '[{"op":"remove","path":"/spec/selector/rollouts-pod-template-hash"}]'
````
```

#### Block 14 — docs/diagrams/rollout-blue-green/source.html: the figure's page

<!-- block: docs/diagrams/rollout-blue-green/source.html | create -->
```html
<title>Blue-Green Rollout</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>
:root {
  --ground: #f5f6f8; --surface: #ffffff; --ink: #18212c; --muted: #58636f; --rule: #d7dce3; --lane: #f0f2f5;
  --pipe: #0e6f68; --ctl: #6a44b0; --data: #a55a0b; --data-wash: #fbf1e4;
  --blue: #2457a8; --blue-wash: #e6eefb; --green: #2c7a3f; --green-wash: #e5f4e8;
  --gap: #b3261e; --gap-wash: #fbe9e7;
  --font-body: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, "SF Mono", Menlo, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --ground: #0e131a; --surface: #151c25; --ink: #e5e9ef; --muted: #9aa5b3; --rule: #2a3440; --lane: #111821;
    --pipe: #3fcfc0; --ctl: #b79cf0; --data: #f0a53c; --data-wash: #2a2014;
    --blue: #7fa9f0; --blue-wash: #16223a; --green: #74cf8a; --green-wash: #14281a;
    --gap: #f2857c; --gap-wash: #2d1614;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --ground: #0e131a; --surface: #151c25; --ink: #e5e9ef; --muted: #9aa5b3; --rule: #2a3440; --lane: #111821;
  --pipe: #3fcfc0; --ctl: #b79cf0; --data: #f0a53c; --data-wash: #2a2014;
  --blue: #7fa9f0; --blue-wash: #16223a; --green: #74cf8a; --green-wash: #14281a;
  --gap: #f2857c; --gap-wash: #2d1614;
}
* { box-sizing: border-box; }
body { background: var(--ground); color: var(--ink); font-family: var(--font-body); font-size: 15px; line-height: 1.55; margin: 0; }
.page { max-width: 1160px; margin: 0 auto; padding-inline: 16px; padding-block: 32px 56px; display: grid; gap: 28px; }
header { display: grid; gap: 10px; }
.eyebrow { font-family: var(--font-mono); font-size: 12px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
h1 { font-size: clamp(24px, 4vw, 34px); line-height: 1.15; margin: 0; font-weight: 700; text-wrap: balance; }
p { margin: 0; max-width: 72ch; }
code { font-family: var(--font-mono); font-size: .9em; }
figure { margin: 0; display: grid; gap: 10px; }
.fig-scroll { overflow-x: auto; background: var(--surface); border: 1px solid var(--rule); border-radius: 10px; padding: 12px; }
.fig-scroll svg { display: block; width: 100%; min-width: 820px; height: auto; color: var(--ink); }
figcaption { font-size: 13.5px; color: var(--muted); max-width: 80ch; }
</style>

<div class="page">
  <header>
    <div class="eyebrow">group-sync-dashboard · blue-green · #426</div>
    <h1>Blue-green with Argo Rollouts: green migrates its own copy before the switch</h1>
    <p>Each version (a colour) opens its own database on the data claim. Green starts from blue's newest copy
      and migrates that copy while blue keeps serving. The switch moves the active Service to green; the Route
      does not change. An abort leaves blue exactly as it was.</p>
  </header>

  <figure>
    <div class="fig-scroll">
      <svg viewBox="0 0 1120 950" role="img" aria-label="Seven lanes, time flowing down: the release's values file and its deployment pipeline, the Argo Rollouts controller, the Route and Services, blue, green, the data claim, and the report service. At rest the Route reaches blue through the active Service, and blue's leader writes copies of its database that the report service reads. A new image in the release's values file, rolled out by its pipeline, changes the Deployment's template; the controller creates green and points the preview Service at it. Green's init container copies blue's newest copy into its own directory; the dashboard then takes the pre-upgrade copy and migrates green's copy, while blue keeps serving and writing its own file. The Rollout pauses until the values file promotes it. An abort, the previous image back in the values file, scales green down and leaves blue untouched, so nothing is restored. Promotion moves the active Service to green; blue is scaled down after 30 seconds and its directory is kept; green takes the lease and writes the copies the report service reads. An undo brings blue back on the newest copy it can read, or its own file. With no controller the Rollout is inert and the Deployment keeps serving. The controller is a cluster prerequisite, not shipped by the chart.">
        <defs>
          <marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="currentColor"/></marker>
          <marker id="ah-pipe" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="var(--pipe)"/></marker>
          <marker id="ah-ctl" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="var(--ctl)"/></marker>
          <marker id="ah-data" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="var(--data)"/></marker>
          <marker id="ah-gap" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="var(--gap)"/></marker>
          <marker id="ah-alt" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="var(--muted)"/></marker>
        </defs>
        <!-- lanes: the controller's namespace, then the release namespace's objects -->
        <g fill="var(--lane)">
          <rect x="0" y="0" width="160" height="950"/><rect x="320" y="0" width="160" height="950"/>
          <rect x="640" y="0" width="160" height="950"/><rect x="960" y="0" width="160" height="950"/>
        </g>
        <g stroke="var(--rule)">
          <line x1="160" y1="0" x2="160" y2="950"/><line x1="320" y1="0" x2="320" y2="950"/><line x1="480" y1="0" x2="480" y2="950"/>
          <line x1="640" y1="0" x2="640" y2="950"/><line x1="800" y1="0" x2="800" y2="950"/><line x1="960" y1="0" x2="960" y2="950"/>
        </g>
        <g font-family="IBM Plex Mono, monospace" font-size="11.5" font-weight="600" fill="var(--muted)" text-anchor="middle">
          <text x="80" y="24">VALUES · PIPELINE</text>
          <text x="240" y="24">ROLLOUTS CONTROLLER</text>
          <text x="400" y="24">ROUTE · SERVICES</text>
          <text x="560" y="24" fill="var(--blue)">BLUE · RUNNING</text>
          <text x="720" y="24" fill="var(--green)">GREEN · NEW</text>
          <text x="880" y="24">DATA CLAIM /data</text>
          <text x="1040" y="24">REPORT · CRONJOBS</text>
        </g>
        <g font-family="IBM Plex Sans, sans-serif" font-size="10.5" fill="var(--muted)" text-anchor="middle">
          <text x="240" y="40">the cluster's, not this chart's</text>
          <text x="720" y="40">the five lanes on the right run in the dashboard's namespace</text>
        </g>

        <g font-family="IBM Plex Sans, sans-serif" font-size="11.5" fill="currentColor" text-anchor="middle">
          <!-- at rest -->
          <rect x="168" y="56" width="144" height="58" rx="6" fill="var(--surface)" stroke="currentColor" stroke-width="1.2" stroke-dasharray="5 4"/>
          <text x="240" y="74" font-weight="600">Argo Rollouts controller</text>
          <text x="240" y="90">prerequisite, one per</text>
          <text x="240" y="105">cluster: not in this chart</text>
          <rect x="168" y="130" width="144" height="58" rx="6" fill="var(--gap-wash)" stroke="var(--gap)" stroke-width="1"/>
          <text x="240" y="148" font-weight="600" fill="var(--gap)">no controller:</text>
          <text x="240" y="164" fill="var(--gap)">the Rollout is inert,</text>
          <text x="240" y="179" fill="var(--gap)">the Deployment serves</text>
          <line x1="240" y1="114" x2="240" y2="127" stroke="var(--gap)" stroke-width="1" marker-end="url(#ah-gap)"/>
          <text x="248" y="124" text-anchor="start" font-size="10" fill="var(--gap)">absent</text>

          <rect x="328" y="56" width="144" height="62" rx="6" fill="var(--surface)" stroke="currentColor" stroke-width="1.2"/>
          <text x="400" y="74" font-weight="600">Route → active Svc</text>
          <text x="400" y="90">active → blue</text>
          <text x="400" y="106">preview → blue too</text>
          <rect x="488" y="56" width="144" height="62" rx="6" fill="var(--blue-wash)" stroke="var(--blue)" stroke-width="1.5"/>
          <text x="560" y="74" font-weight="600" fill="var(--blue)">blue serves</text>
          <text x="560" y="90">holds the lease, polls,</text>
          <text x="560" y="106">writes rs-blue/gsd.db</text>
          <line x1="472" y1="87" x2="484" y2="87" stroke="currentColor" stroke-width="1.2" marker-end="url(#ah)"/>
          <rect x="808" y="56" width="144" height="80" rx="6" fill="var(--data-wash)" stroke="var(--data)" stroke-width="1.5"/>
          <text x="880" y="74" font-weight="600" fill="var(--data)">rs-blue/gsd.db</text>
          <text x="880" y="90">copies by the leader:</text>
          <text x="880" y="106">report/ every 5 min</text>
          <text x="880" y="122">backup/ every 6 h</text>
          <line x1="632" y1="96" x2="804" y2="96" stroke="var(--data)" stroke-width="1.5" marker-end="url(#ah-data)"/>
          <text x="718" y="90" fill="var(--data)" font-size="10.5">writes, copies</text>
          <rect x="968" y="56" width="144" height="62" rx="6" fill="var(--surface)" stroke="currentColor" stroke-width="1.2"/>
          <text x="1040" y="74" font-weight="600">report service</text>
          <text x="1040" y="90">reads the newest copy;</text>
          <text x="1040" y="106">CronJobs trigger it</text>
          <line x1="952" y1="87" x2="964" y2="87" stroke="var(--data)" stroke-width="1.5" marker-end="url(#ah-data)"/>

          <!-- a new image -->
          <rect x="8" y="210" width="144" height="66" rx="6" fill="var(--surface)" stroke="var(--pipe)" stroke-width="1.5"/>
          <text x="80" y="228" font-weight="600" fill="var(--pipe)">new image in the</text>
          <text x="80" y="244">values file; rolled out</text>
          <text x="80" y="259">to the Deployment</text>
          <text x="80" y="272" font-size="10.5" fill="var(--muted)">0 pods: none start</text>
          <rect x="168" y="210" width="144" height="64" rx="6" fill="var(--surface)" stroke="var(--ctl)" stroke-width="1.5"/>
          <text x="240" y="228" font-weight="600" fill="var(--ctl)">sees the template</text>
          <text x="240" y="244">(workloadRef),</text>
          <text x="240" y="260">creates green</text>
          <line x1="152" y1="232" x2="164" y2="232" stroke="var(--pipe)" stroke-width="1.5" marker-end="url(#ah-pipe)"/>
          <path d="M80,276 L80,302 L964,302" stroke="var(--pipe)" stroke-width="1.5" fill="none" marker-end="url(#ah-pipe)"/>
          <text x="560" y="296" fill="var(--pipe)" font-size="10.5">the report Deployment rolls at once</text>
          <rect x="968" y="286" width="144" height="74" rx="6" fill="var(--surface)" stroke="currentColor" stroke-width="1.2"/>
          <text x="1040" y="304" font-weight="600">new report service</text>
          <text x="1040" y="320">reads blue's older</text>
          <text x="1040" y="336">copy: older is</text>
          <text x="1040" y="350" font-size="10.5">accepted, newer refused</text>

          <!-- green comes up on its own copy -->
          <path d="M312,244 L720,244 L720,326" stroke="var(--ctl)" stroke-width="1.5" fill="none" marker-end="url(#ah-ctl)"/>
          <path d="M312,264 L400,264 L400,326" stroke="var(--ctl)" stroke-width="1.5" fill="none" marker-end="url(#ah-ctl)"/>
          <text x="560" y="238" fill="var(--ctl)" font-size="10.5">green's ReplicaSet</text>
          <rect x="328" y="330" width="144" height="48" rx="6" fill="var(--surface)" stroke="currentColor" stroke-width="1.2"/>
          <text x="400" y="349" font-weight="600">preview → green</text>
          <text x="400" y="366">active stays on blue</text>
          <rect x="648" y="330" width="144" height="64" rx="6" fill="var(--green-wash)" stroke="var(--green)" stroke-width="1.5"/>
          <text x="720" y="348" font-weight="600" fill="var(--green)">1 · colour-seed</text>
          <text x="720" y="364">copies the newest copy</text>
          <text x="720" y="380">to rs-green/, verified</text>
          <path d="M880,136 L880,362 L796,362" stroke="var(--data)" stroke-width="1.5" fill="none" marker-end="url(#ah-data)"/>
          <text x="886" y="250" text-anchor="start" fill="var(--data)" font-size="10.5">newest</text>
          <text x="886" y="264" text-anchor="start" fill="var(--data)" font-size="10.5">copy</text>
          <rect x="648" y="410" width="144" height="82" rx="6" fill="var(--green-wash)" stroke="var(--green)" stroke-width="1.5"/>
          <text x="720" y="428" font-weight="600" fill="var(--green)">2 · the migration</text>
          <text x="720" y="444">#301 copy, then</text>
          <text x="720" y="460">migrates green's copy</text>
          <text x="720" y="476">only, before the switch</text>
          <line x1="720" y1="394" x2="720" y2="406" stroke="var(--green)" stroke-width="1.2" marker-end="url(#ah)"/>
          <rect x="808" y="424" width="144" height="54" rx="6" fill="var(--data-wash)" stroke="var(--data)" stroke-width="1.5"/>
          <text x="880" y="442" font-weight="600" fill="var(--data)">rs-green/gsd.db</text>
          <text x="880" y="458">rs-green/pre-upgrade/</text>
          <line x1="792" y1="451" x2="804" y2="451" stroke="var(--data)" stroke-width="1.5" marker-end="url(#ah-data)"/>
          <rect x="648" y="508" width="144" height="46" rx="6" fill="var(--green-wash)" stroke="var(--green)" stroke-width="1.5"/>
          <text x="720" y="527">ready; not the lease</text>
          <text x="720" y="543">holder, so no polling</text>
          <line x1="720" y1="492" x2="720" y2="504" stroke="var(--green)" stroke-width="1.2" marker-end="url(#ah)"/>
          <rect x="488" y="410" width="144" height="112" rx="6" fill="var(--blue-wash)" stroke="var(--blue)" stroke-width="1.5"/>
          <text x="560" y="428" font-weight="600" fill="var(--blue)">meanwhile, blue</text>
          <text x="560" y="444">serves the Route,</text>
          <text x="560" y="460">polls, writes only</text>
          <text x="560" y="476">rs-blue/ and copies;</text>
          <text x="560" y="492">never sees green's</text>
          <text x="560" y="508">new schema</text>

          <!-- the pause, and the abort -->
          <rect x="168" y="576" width="144" height="64" rx="6" fill="var(--surface)" stroke="var(--ctl)" stroke-width="1.5"/>
          <text x="240" y="594" font-weight="600" fill="var(--ctl)">paused</text>
          <text x="240" y="610">green is checked on</text>
          <text x="240" y="626">the preview Service</text>
          <line x1="240" y1="274" x2="240" y2="572" stroke="var(--ctl)" stroke-width="1.5" marker-end="url(#ah-ctl)"/>
          <text x="246" y="430" text-anchor="start" fill="var(--ctl)" font-size="10.5">green ready</text>
          <path d="M312,608 L644,608" stroke="var(--gap)" stroke-width="1" fill="none" marker-end="url(#ah-gap)"/>
          <text x="478" y="602" fill="var(--gap)" font-size="10.5">abort: previous image back</text>
          <rect x="648" y="572" width="144" height="90" rx="6" fill="var(--gap-wash)" stroke="var(--gap)" stroke-width="1"/>
          <text x="720" y="590" font-weight="600" fill="var(--gap)">green scaled down;</text>
          <text x="720" y="606" fill="var(--gap)">rs-green/ stays</text>
          <text x="720" y="622" fill="var(--gap)">until pruned.</text>
          <text x="720" y="638" fill="var(--gap)">Blue never migrated:</text>
          <text x="720" y="652" fill="var(--gap)" font-size="10.5">nothing to restore</text>

          <!-- the switch -->
          <rect x="168" y="690" width="144" height="62" rx="6" fill="var(--surface)" stroke="var(--ctl)" stroke-width="2"/>
          <text x="240" y="709" font-weight="700" fill="var(--ctl)">promote</text>
          <text x="240" y="725">the values file sets</text>
          <text x="240" y="741" font-size="10.5">autoPromotionEnabled: true</text>
          <line x1="240" y1="640" x2="240" y2="686" stroke="var(--ctl)" stroke-width="1.5" marker-end="url(#ah-ctl)"/>
          <line x1="312" y1="712" x2="324" y2="712" stroke="var(--ctl)" stroke-width="1.5" marker-end="url(#ah-ctl)"/>
          <rect x="328" y="686" width="144" height="62" rx="6" fill="var(--surface)" stroke="currentColor" stroke-width="1.2"/>
          <text x="400" y="704" font-weight="600">active → green</text>
          <text x="400" y="720">the Route is</text>
          <text x="400" y="736">unchanged</text>
          <path d="M400,748 L400,768 L720,768 L720,752" stroke="currentColor" stroke-width="1.2" fill="none" marker-end="url(#ah)"/>
          <text x="560" y="762" font-size="10.5">requests</text>
          <rect x="488" y="686" width="144" height="62" rx="6" fill="var(--blue-wash)" stroke="var(--blue)" stroke-width="1.5"/>
          <text x="560" y="704" font-weight="600" fill="var(--blue)">30 s later, blue</text>
          <text x="560" y="720">scaled to 0; rs-blue/</text>
          <text x="560" y="736">kept for an undo</text>
          <rect x="648" y="686" width="144" height="62" rx="6" fill="var(--green-wash)" stroke="var(--green)" stroke-width="1.5"/>
          <text x="720" y="704" font-weight="600" fill="var(--green)">green serves</text>
          <text x="720" y="720">lease within 45 s:</text>
          <text x="720" y="736">polls, writes copies</text>
          <line x1="792" y1="708" x2="804" y2="708" stroke="var(--data)" stroke-width="1.5" marker-end="url(#ah-data)"/>
          <rect x="808" y="686" width="144" height="46" rx="6" fill="var(--data-wash)" stroke="var(--data)" stroke-width="1.5"/>
          <text x="880" y="705">report/, backup/:</text>
          <text x="880" y="721">green's copies now</text>
          <line x1="952" y1="708" x2="964" y2="708" stroke="var(--data)" stroke-width="1.5" marker-end="url(#ah-data)"/>
          <rect x="968" y="686" width="144" height="46" rx="6" fill="var(--surface)" stroke="currentColor" stroke-width="1.2"/>
          <text x="1040" y="705">reads green's</text>
          <text x="1040" y="721">copies</text>

          <!-- an undo after the switch -->
          <rect x="8" y="800" width="144" height="46" rx="6" fill="var(--surface)" stroke="var(--muted)" stroke-width="1"/>
          <text x="80" y="819">undo: previous image</text>
          <text x="80" y="835">in the values file</text>
          <path d="M152,823 L484,823" stroke="var(--muted)" stroke-width="1" fill="none" marker-end="url(#ah-alt)"/>
          <rect x="488" y="796" width="144" height="80" rx="6" fill="var(--surface)" stroke="var(--muted)" stroke-width="1"/>
          <text x="560" y="814" font-weight="600" fill="var(--muted)">blue returns on</text>
          <text x="560" y="830">the newest copy if it</text>
          <text x="560" y="846">can read its schema,</text>
          <text x="560" y="862">else its own rs-blue/</text>
        </g>

        <!-- the key -->
        <g font-family="IBM Plex Sans, sans-serif" font-size="11.5" fill="var(--muted)">
          <text x="660" y="800" font-weight="600" fill="currentColor">Everything drawn ships in #426, except the dashed box.</text>
          <line x1="660" y1="820" x2="690" y2="820" stroke="var(--pipe)" stroke-width="1.5"/><text x="698" y="824">the pipeline rolls out the values file</text>
          <line x1="660" y1="840" x2="690" y2="840" stroke="var(--ctl)" stroke-width="1.5"/><text x="698" y="844">the Rollouts controller acts</text>
          <line x1="660" y1="860" x2="690" y2="860" stroke="currentColor" stroke-width="1.2"/><text x="698" y="864">requests, Route to pod</text>
          <line x1="660" y1="880" x2="690" y2="880" stroke="var(--data)" stroke-width="1.5"/><text x="698" y="884">a database file or copy is written or read</text>
          <line x1="660" y1="900" x2="690" y2="900" stroke="var(--gap)" stroke-width="1"/><text x="698" y="904">nothing switches: abort, or no controller</text>
          <line x1="660" y1="920" x2="690" y2="920" stroke="var(--muted)" stroke-width="1"/><text x="698" y="924">an undo after the switch</text>
          <rect x="660" y="932" width="30" height="12" rx="3" fill="none" stroke="currentColor" stroke-dasharray="5 4"/><text x="698" y="942">a cluster prerequisite</text>
          <text x="1112" y="942" text-anchor="end">time flows down</text>
        </g>
      </svg>
    </div>
    <figcaption>Blue and green never open the same database file: each ReplicaSet has its own directory on the data
      claim. The migration runs in green, on green's copy, before the switch. The report service and its CronJobs are
      a plain Deployment that rolls at the sync and reads whichever colour's leader wrote the newest copy.</figcaption>
  </figure>
</div>
```

#### Block 15 — docs/README.md: the guide in the docs index

<!-- block: docs/README.md | edit -->
```markdown
- [TROUBLESHOOTING_auditor_groups.md](TROUBLESHOOTING_auditor_groups.md) — auditor groups, `createLocal` and LDAP GroupSync collisions.
- [RUNBOOK_backup_restore.md](RUNBOOK_backup_restore.md) — back up and restore the dashboard's history.
- [RUNBOOK.md](../charts/group-sync-dashboard/RUNBOOK.md) — a remote cluster's connection is broken: find out why, then Refresh and Rejoin; kept beside the chart's values.

```

```markdown
- [TROUBLESHOOTING_auditor_groups.md](TROUBLESHOOTING_auditor_groups.md) — auditor groups, `createLocal` and LDAP GroupSync collisions.
- [RUNBOOK_backup_restore.md](RUNBOOK_backup_restore.md) — back up and restore the dashboard's history.
- [BLUE_GREEN.md](BLUE_GREEN.md) — blue-green releases with Argo Rollouts: turn it on and off, promote, abort, undo.
- [RUNBOOK.md](../charts/group-sync-dashboard/RUNBOOK.md) — a remote cluster's connection is broken: find out why, then Refresh and Rejoin; kept beside the chart's values.

```

#### Block 16 — docs/CHANGELOG.md: the entry under Unreleased

<!-- block: docs/CHANGELOG.md | edit -->
```markdown

## Unreleased

- **The runbook says which card rows are the last poll's (Epic D composition review, K5).** Refresh stores nothing
```

```markdown

## Unreleased

- **Blue-green releases with Argo Rollouts, off by default (#426, SPEC_W1, chart 0.62.0).** `rollout.enabled`
  renders a Rollout that takes its pods from the Deployment (`workloadRef`, `scaleDown: onsuccess`), a preview
  Service and a seed script. Each version opens its own database, seeded from the running version's newest copy,
  so the migration runs on green's copy before the switch. With no Rollouts controller the Deployment keeps
  serving. Promotion is `rollout.autoPromotionEnabled: true` in the release's values file; an abort or an undo is
  the previous image. `docs/BLUE_GREEN.md` is the guide, with the data window it costs. The default render is
  unchanged apart from the chart label.

- **The runbook says which card rows are the last poll's (Epic D composition review, K5).** Refresh stores nothing
```

#### Block 17 — local-development/tests/test_colour_seed_script.py: the seed script's tests, T426-12 and T426-14

<!-- block: local-development/tests/test_colour_seed_script.py | create -->
```python
"""The blue-green seed script, against real VACUUM INTO copies (docs/BLUE_GREEN.md, SPEC_W1).

Loaded from the chart directory, like the offsite script: the chart ships it as a ConfigMap, so the test
runs the exact bytes that ship. Each test is one row of the script's decision table.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import sqlite3
import time

import pytest

from gsd.store import Store

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "charts" / "group-sync-dashboard" / "scripts" / "colour_seed.py"


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("colour_seed", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_db(path: pathlib.Path, events: int) -> None:
    """A database the way the dashboard makes one, with `events` sync events to tell copies apart."""
    store = Store(str(path))
    store.upsert_cluster("crc", "https://api.crc.testing:6443", True)
    for i in range(events):
        store.record_sync_event("crc", "corp", "ns", f"2026-09-27T10:{i:02d}:00Z", "2026-09-27T10:00:30Z", "0 * * * *", i)
    store.close()


def make_copy(data: pathlib.Path, events: int, *, into: str = "report", schema: int | None = None) -> pathlib.Path:
    """A copy as the running colour's leader writes it, optionally stamped with another schema."""
    src = data / f"leader-{events}" / "gsd.db"
    src.parent.mkdir(parents=True)
    make_db(src, events)
    store = Store(str(src))
    copy = pathlib.Path(store.snapshot(str(data / into), keep=10))
    store.close()
    for leftover in src.parent.iterdir():
        leftover.unlink()
    src.parent.rmdir()
    if schema is not None:
        conn = sqlite3.connect(copy)
        conn.execute(f"PRAGMA user_version = {schema}")
        conn.commit()
        conn.close()
    return copy


def events_in(db: pathlib.Path) -> int:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return conn.execute("SELECT COUNT(*) FROM sync_event").fetchone()[0]
    finally:
        conn.close()


def age(directory: pathlib.Path, seconds: float) -> None:
    """Move the colour's last write `seconds` into the past (negative: the future)."""
    when = time.time() - seconds
    for name in ("gsd.db", "gsd.db-wal"):
        if (directory / name).exists():
            os.utime(directory / name, (when, when))


def run(script, data: pathlib.Path, colour: str = "rs-green") -> int:
    return script.main(["--db", str(data / colour / "gsd.db"),
                        "--from", str(data / "report"), "--from", str(data / "backup")])


def test_a_new_colour_starts_from_the_newest_copy_verified(script, tmp_path, capsys):
    make_copy(tmp_path, 3)
    assert run(script, tmp_path) == 0
    assert events_in(tmp_path / "rs-green" / "gsd.db") == 3
    assert "seeded" in capsys.readouterr().out
    assert not list((tmp_path / "rs-green").glob("*.seed"))


def test_the_seed_log_names_the_copy_and_its_age(script, tmp_path, capsys):
    """T426-14: the data window begins at the copy green starts from, so the log says which and how old."""
    copy = make_copy(tmp_path, 3)
    old = copy.with_name("gsd-20260101T000000.000000Z.db")
    copy.rename(old)
    assert run(script, tmp_path) == 0
    out = capsys.readouterr().out
    age = int(out.split("the copy was written ", 1)[1].split(" s ago", 1)[0])
    assert old.name in out and age >= 86400


def test_a_copy_named_with_a_pod_after_its_stamp_still_parses(script, tmp_path):
    """Above one replica a copy carries the pod after the stamp; the stamp alone is read."""
    copy = make_copy(tmp_path, 3)
    make_db(tmp_path / "rs-green" / "gsd.db", 7)
    age(tmp_path / "rs-green", 600)
    copy.rename(copy.with_name(copy.name[:-len(".db")] + "-group-sync-dashboard-6d4f-x2.db"))
    assert run(script, tmp_path) == 0
    assert events_in(tmp_path / "rs-green" / "gsd.db") == 3


def test_the_newest_copy_is_chosen_by_name_across_both_directories(script, tmp_path):
    make_copy(tmp_path, 2, into="report")
    make_copy(tmp_path, 5, into="backup")
    assert run(script, tmp_path) == 0
    assert events_in(tmp_path / "rs-green" / "gsd.db") == 5


def test_an_empty_volume_is_a_new_install(script, tmp_path, capsys):
    assert run(script, tmp_path) == 0
    assert not (tmp_path / "rs-green" / "gsd.db").exists()
    assert "starts empty" in capsys.readouterr().out


def test_a_database_without_a_copy_is_refused_never_started_empty(script, tmp_path, capsys):
    make_db(tmp_path / "gsd.db", 4)
    assert run(script, tmp_path) == 1
    assert not (tmp_path / "rs-green" / "gsd.db").exists()
    assert "no copy" in capsys.readouterr().err


def test_the_running_colour_keeps_its_own_file_on_a_restart(script, tmp_path):
    make_copy(tmp_path, 3)
    make_db(tmp_path / "rs-green" / "gsd.db", 7)
    age(tmp_path / "rs-green", -60)
    assert run(script, tmp_path) == 0
    assert events_in(tmp_path / "rs-green" / "gsd.db") == 7


def test_a_newer_copy_of_the_same_schema_replaces_the_file_and_sets_it_aside(script, tmp_path):
    make_db(tmp_path / "rs-green" / "gsd.db", 7)
    age(tmp_path / "rs-green", 600)
    make_copy(tmp_path, 3)
    assert run(script, tmp_path) == 0
    assert events_in(tmp_path / "rs-green" / "gsd.db") == 3
    (aside,) = tmp_path.glob("rs-green.set-aside-*")
    assert events_in(aside / "gsd.db") == 7


def test_a_retry_after_an_abort_reseeds_from_the_older_schema(script, tmp_path):
    make_db(tmp_path / "rs-green" / "gsd.db", 7)
    age(tmp_path / "rs-green", 600)
    own = sqlite3.connect(tmp_path / "rs-green" / "gsd.db")
    version = own.execute("PRAGMA user_version").fetchone()[0]
    own.close()
    make_copy(tmp_path, 3, schema=version - 1)
    assert run(script, tmp_path) == 0
    assert events_in(tmp_path / "rs-green" / "gsd.db") == 3


def test_an_undo_past_a_migration_keeps_its_own_file(script, tmp_path, capsys):
    make_db(tmp_path / "rs-blue" / "gsd.db", 7)
    age(tmp_path / "rs-blue", 600)
    own = sqlite3.connect(tmp_path / "rs-blue" / "gsd.db")
    version = own.execute("PRAGMA user_version").fetchone()[0]
    own.close()
    make_copy(tmp_path, 3, schema=version + 1)
    assert run(script, tmp_path, colour="rs-blue") == 0
    assert events_in(tmp_path / "rs-blue" / "gsd.db") == 7
    assert "newer than this file's" in capsys.readouterr().out


def test_a_copy_that_fails_integrity_check_is_refused_and_leaves_nothing(script, tmp_path, capsys):
    copy = make_copy(tmp_path, 3)
    raw = bytearray(copy.read_bytes())
    raw[4096:8192] = b"\xff" * 4096
    copy.write_bytes(bytes(raw))
    assert run(script, tmp_path) == 1
    assert not list((tmp_path / "rs-green").iterdir())
    assert "colour seed refused" in capsys.readouterr().err


def test_prune_keeps_its_own_and_the_four_newest_other_colours(script, tmp_path):
    make_copy(tmp_path, 1)
    for n, seconds in enumerate((600, 500, 400, 300, 200, 100)):
        make_db(tmp_path / f"rs-old{n}" / "gsd.db", 1)
        age(tmp_path / f"rs-old{n}", seconds)
    assert run(script, tmp_path) == 0
    assert sorted(p.name for p in tmp_path.glob("rs-*")) == ["rs-green", "rs-old2", "rs-old3", "rs-old4", "rs-old5"]


def test_a_new_colour_carries_the_fleet_gate_copy_of_the_newest_other_colour(script, tmp_path):
    """#481's backstop lives beside the database and no VACUUM INTO copy carries it (gsd/fleetstate.py#FileBackstop):
    a colour with none takes the newest other colour's, by that colour's last write, before the pre-flag one."""
    make_copy(tmp_path, 3)
    (tmp_path / "fleet-gate.json").write_text('{"pre-flag": {}}')
    for name, seconds, text in (("rs-blue", 60, '{"blue": {}}'), ("rs-older", 600, '{"older": {}}')):
        make_db(tmp_path / name / "gsd.db", 1)
        (tmp_path / name / "fleet-gate.json").write_text(text)
        age(tmp_path / name, seconds)
    assert run(script, tmp_path) == 0
    assert (tmp_path / "rs-green" / "fleet-gate.json").read_text() == '{"blue": {}}'


def test_the_first_colour_carries_the_fleet_gate_copy_from_beside_data_gsd_db(script, tmp_path):
    """The flag just turned on: the copy sat beside /data/gsd.db, and the Deployment's first colour takes it."""
    make_copy(tmp_path, 3)
    make_db(tmp_path / "gsd.db", 1)
    (tmp_path / "fleet-gate.json").write_text('{"pre-flag": {}}')
    assert run(script, tmp_path) == 0
    assert (tmp_path / "rs-green" / "fleet-gate.json").read_text() == '{"pre-flag": {}}'
```

#### Block 18 — local-development/tests/test_chart_rollout.py: the render tests, T426-1 to T426-11

<!-- block: local-development/tests/test_chart_rollout.py | create -->
```python
"""rollout.enabled: blue-green with Argo Rollouts, and what it must never do (docs/BLUE_GREEN.md, SPEC_W1).

Rendered with `helm template`, because the guards and the fail-safe shape ARE the templates. Two properties
carry the design: the Deployment is still rendered with its whole pod template when the flag is on, so a
cluster with the CRD and no controller keeps the dashboard serving; and no two colours share a database file.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest
import yaml

CHART = pathlib.Path(__file__).resolve().parents[2] / "charts" / "group-sync-dashboard"
CRD = ["--api-versions", "argoproj.io/v1alpha1/Rollout"]
NAME = "t-group-sync-dashboard"

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")


def render(*extra: str, crd: bool = True, **values) -> tuple[bool, str]:
    args = ["helm", "template", "t", str(CHART), *(CRD if crd else []), *extra]
    for key, value in values.items():
        args += ["--set", f"{key.replace('__', '.')}={value}"]
    done = subprocess.run(args, capture_output=True, text=True)
    return done.returncode == 0, done.stdout + done.stderr


def objects(out: str) -> dict[tuple[str, str], dict]:
    return {(d["kind"], d["metadata"]["name"]): d for d in yaml.safe_load_all(out) if d}


def on(**values) -> dict[tuple[str, str], dict]:
    ok, out = render(rollout__enabled="true", **values)
    assert ok, out
    return objects(out)


def test_off_by_default_renders_no_rollout_object():
    ok, out = render(crd=False)
    assert ok, out
    kinds = {kind for kind, _ in objects(out)}
    assert "Rollout" not in kinds and ("Service", f"{NAME}-preview") not in objects(out)
    assert objects(out)[("Deployment", NAME)]["spec"]["replicas"] == 1


def test_without_the_crd_the_render_is_refused_and_names_the_prerequisite():
    ok, out = render(crd=False, rollout__enabled="true")
    assert not ok
    assert "RolloutManager" in out and "never creates" in out
    # The way out is a value in the release's values file, never a command (the operator, 2026-10-01).
    assert "set rollout.enabled: false in this release's values file" in out
    assert "--api-versions" not in out and "--set" not in out


def test_the_deployment_still_serves_until_a_controller_makes_the_rollout_healthy():
    rendered = on()
    deployment = rendered[("Deployment", NAME)]
    rollout = rendered[("Rollout", NAME)]
    # No replicas: neither Helm nor Argo CD scales it back up after the controller scales it down.
    assert "replicas" not in deployment["spec"]
    assert [c["name"] for c in deployment["spec"]["template"]["spec"]["containers"]] == ["dashboard", "oauth-proxy"]
    assert rollout["spec"]["workloadRef"] == {
        "apiVersion": "apps/v1", "kind": "Deployment", "name": NAME, "scaleDown": "onsuccess"}
    assert "template" not in rollout["spec"]
    assert "postPromotionAnalysis" not in rollout["spec"]["strategy"]["blueGreen"]


def test_with_no_controller_the_route_still_reaches_the_deployments_pod():
    rendered = on()
    route = rendered[("Route", NAME)]
    service = rendered[("Service", route["spec"]["to"]["name"])]
    pod_labels = rendered[("Deployment", NAME)]["spec"]["template"]["metadata"]["labels"]
    assert service["spec"]["selector"].items() <= pod_labels.items()
    assert rendered[("Rollout", NAME)]["spec"]["strategy"]["blueGreen"]["activeService"] == service["metadata"]["name"]


def test_every_replicaset_opens_its_own_database_seeded_first():
    spec = on()[("Deployment", NAME)]["spec"]["template"]["spec"]
    for container in (spec["initContainers"][0], spec["containers"][0]):
        env = [e["name"] for e in container["env"]]
        path = next(e["value"] for e in container["env"] if e["name"] == "GSD_DB_PATH")
        assert path == "/data/rs-$(ROLLOUTS_POD_TEMPLATE_HASH)$(POD_TEMPLATE_HASH)/gsd.db"
        # Kubernetes expands $(VAR) only against variables defined earlier in the list.
        assert env.index("ROLLOUTS_POD_TEMPLATE_HASH") < env.index("GSD_DB_PATH")
        assert env.index("POD_TEMPLATE_HASH") < env.index("GSD_DB_PATH")
    seed = spec["initContainers"][0]
    assert seed["command"] == ["python3.14", "/scripts/colour_seed.py", "--db", "$(GSD_DB_PATH)",
                               "--from", "/data/report", "--from", "/data/backup"]
    assert seed["image"] == spec["containers"][0]["image"]


def test_the_seed_reads_only_the_copies_that_are_on():
    seed = on(reporting__enabled="false")[("Deployment", NAME)]["spec"]["template"]["spec"]["initContainers"][0]
    assert seed["command"][4:] == ["--from", "/data/backup"]


def test_the_preview_service_selects_the_pods_and_escapes_the_servicemonitor():
    rendered = on(monitoring__serviceMonitor__enabled="true")
    preview = rendered[("Service", f"{NAME}-preview")]
    monitor = rendered[("ServiceMonitor", NAME)]
    assert preview["spec"]["selector"] == rendered[("Service", NAME)]["spec"]["selector"]
    assert not monitor["spec"]["selector"]["matchLabels"].items() <= preview["metadata"]["labels"].items()
    assert "annotations" not in preview["metadata"]


def test_the_configmap_carries_the_script_verbatim():
    cm = on()[("ConfigMap", f"{NAME}-colour-seed")]
    assert cm["data"]["colour_seed.py"] == (CHART / "scripts" / "colour_seed.py").read_text()


def test_the_rollout_keeps_one_old_colour_and_waits_for_a_person_by_default():
    blue_green = on()[("Rollout", NAME)]["spec"]["strategy"]["blueGreen"]
    assert blue_green == {"activeService": NAME, "previewService": f"{NAME}-preview",
                          "autoPromotionEnabled": False, "scaleDownDelaySeconds": 30,
                          "scaleDownDelayRevisionLimit": 1}


def test_the_rollout_adds_no_rbac():
    def rbac(out: str) -> list[dict]:
        return sorted((d for d in yaml.safe_load_all(out) if d and d["kind"] in
                       ("Role", "ClusterRole", "RoleBinding", "ClusterRoleBinding")),
                      key=lambda d: (d["kind"], d["metadata"]["name"]))
    ok_off, off = render()
    ok_on, flag_on = render(rollout__enabled="true")
    assert ok_off and ok_on
    assert rbac(off) == rbac(flag_on)


@pytest.mark.parametrize("values,reason", [
    ({"replicaCount": "2", "leaderElection__enabled": "false", "reporting__enabled": "false"}, "Set replicaCount: 1"),
    ({"persistence__accessMode": "ReadWriteOncePod", "reporting__enabled": "false"}, "ReadWriteMany"),
    ({"persistence__accessMode": "ReadWriteOnce", "reporting__enabled": "false"}, "ReadWriteMany"),
    ({"persistence__enabled": "false", "reporting__enabled": "false"}, "Set persistence.enabled: true"),
    ({"leaderElection__enabled": "false"}, "Set leaderElection.enabled: true"),
    ({"rollout__strategy": "canary"}, "Set rollout.strategy: blueGreen"),
    ({"reporting__enabled": "false", "config__backup__enabled": "false"}, "a copy for green to start from"),
    # SPEC_E2's recovery mode (#303): nil-safe, so it holds before and after `recovery` is a value on main.
    ({"recovery__enabled": "true"}, "Turn blue-green off first"),
], ids=["replicas", "rwop", "rwo", "no-persistence", "no-election", "canary", "no-seed-source", "recovery"])
def test_an_unsafe_combination_is_refused(values, reason):
    ok, out = render(rollout__enabled="true", **values)
    assert not ok
    assert reason in out


def test_the_guide_names_the_recovery_refusal_and_the_lease_flip_during_the_preview():
    """Two cases the design has to state: the refusal of recovery mode with the flag on (SPEC_E2), and blue losing
    the lease to green during a preview (the chart refuses this shape at replicaCount > 1 for the same reason)."""
    guide = (CHART.parents[1] / "docs" / "BLUE_GREEN.md").read_text()
    assert "| `recovery.enabled: true` |" in guide
    assert "## Blue loses the lease during the preview" in guide
```

#### Block 19 — local-development/tests/test_values_defaults.py: the two false defaults as stated exceptions, T426-13

<!-- block: local-development/tests/test_values_defaults.py | edit -->
```python
    "reporting.window.enabled": "P4: an operational rail the operator opts into (a timezone + hours + days); off = automated runs are never gated",
    "clusterConfig.secrets.writes.enabled": "S2 (#230): a write path on Secrets widens the dashboard's read-only posture; off until the operator turns it on — default pending the operator's A/B call of 2026-09-20; B flips the default and removes this exception",
}

```

```python
    "reporting.window.enabled": "P4: an operational rail the operator opts into (a timezone + hours + days); off = automated runs are never gated",
    "clusterConfig.secrets.writes.enabled": "S2 (#230): a write path on Secrets widens the dashboard's read-only posture; off until the operator turns it on — default pending the operator's A/B call of 2026-09-20; B flips the default and removes this exception",
    "rollout.enabled": "W1 (#426): needs the cluster's Argo Rollouts controller, a RolloutManager this chart never creates",
    "rollout.autoPromotionEnabled": "W1 (#426): the preview exists so a person checks green before the switch",
}

```
