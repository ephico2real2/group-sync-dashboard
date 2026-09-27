# SPEC W1 — blue-green with Argo Rollouts, off by default: each version opens its own database, so the migration runs on green's copy before the switch, and a missing controller leaves the Deployment serving (#426)

| | |
|---|---|
| Programme | Epic E (#385), restore tools and release safety |
| Batch | W — workload strategy |
| Release | — (post-programme; Epic E, milestone 3.0.0) |
| Version on release | chart 0.60.0 (chart only: no image input changes, so no app version) |
| Issue | [#426](https://github.com/ephico2real2/group-sync-dashboard/issues/426) |
| Status | specified |
| Source | OB1-lite's specification of 2026-09-27, written before any code from issue #426 in full (the body, the research comment of 2026-09-27) and the orchestrator's three follow-up directions of the same day (the RolloutManager is a cluster prerequisite; flag on with no controller must fail safe; the figure in #410's format), main `22a485c` (application 1.0.0, chart 0.59.2), the upstream and Red Hat documents in §3.2, read-only measurements of the lab (§3.3) and hermetic measurements of the store (§3.4). §8's blocks were cut from a copy of `22a485c` with the design implemented, and applied back to a clean copy for the proof in §6. No cluster, branch or GitHub setting was changed. Background work (the operator, 2026-09-27): reviewed, then parked as a ready spec; nothing is merged or deployed now |

## How to read this spec

Read §1 and §2 first: what is being built, and every word defined once. §4.1 answers the operator's concern, the
database migrations, by comparing the four options against the store's code. §4.2 chooses the chart's shape. §4.3
answers the design questions, one row each. §5 says what enforces "no two writers on one file" and what it does not
cover. §6 is the test table, before and after. §7 is the lab walk for the implementing pull request. §8 is the whole
change as implementation blocks (`docs/specs/README.md`, "Implementation blocks"), in apply order:

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_W1_rollout_blue_green.md . --apply

Line citations are plain text, file:line, at `22a485c`. This spec's index row and its header's Status move by hand:
the implementing commit sets both to `merged` beside the applied blocks.

## Orchestrator's notes

**How the orchestrator's three directions of 2026-09-27 are answered:**

1. **The RolloutManager is a cluster prerequisite** (the operator: *"Group sync dashboard just consumes it"*; it is
   filed as ephico2real2/openshift-gitops-helm-chart#2). The chart never renders one. It requires the Rollout API
   (`.Capabilities.APIVersions.Has "argoproj.io/v1alpha1/Rollout"`) and fails with the prerequisite's name and Red
   Hat's document when it is absent (§4.3 k). The figure draws the controller as a dashed box, "prerequisite, one per
   cluster: not in this chart", and the key says the dashed box is the only thing drawn that does not ship.
2. **Flag on, no controller, must fail safe.** It does: the Rollout takes its pods from the Deployment through
   `workloadRef` with `scaleDown: onsuccess`, and the chart keeps rendering the whole Deployment (§4.2). Only the
   controller scales the Deployment down, so without one the Deployment keeps serving. A §4.3 row, a red box in the
   figure, a section of `docs/BLUE_GREEN.md` and two tests pin it
   (`test_the_deployment_still_serves_until_a_controller_makes_the_rollout_healthy`,
   `test_with_no_controller_the_route_still_reaches_the_deployments_pod`).
3. **The figure** follows #410's approved shape: seven lanes, time flowing down, labelled arrows, one line style per
   meaning (six, listed in the key), and the key inside the figure. Rendered light and dark, both PNGs read, and
   `375 px viewport: scrollWidth 375`.

**Retractions, from measurement:**

- *I retract "every open of the store writes to the file".* Measured (§3.4): an open of a database already at schema 20
  makes `total_changes` 0 and leaves the file's sha256 unchanged. The two-writer risk comes instead from the migration
  a new image runs on open, and from the activity flush every replica runs whether or not it leads (§3.1).
- *I retract the first shape, one template that renders a Rollout instead of the Deployment.* The fail-safe direction
  refutes it: with the flag on and no controller it would delete the only serving workload and start nothing (§4.2).

**Versions.** The design changes no image input (`publish.yml`'s `on.push.paths`): the seed is a chart script, like
`scripts/offsite_backup.py`, and the store is unchanged. So #427's check "App image changes bump the app version"
requires no application bump, and the brief's "1.2.0 or the next free MINOR" does not apply. The chart takes the next
MINOR, 0.60.0, for a new value (`test_chart_versions.py`, the chart's convention). If #430 (chart 0.59.3) merges first,
0.60.0 is still the next MINOR.

**Two collisions with #430 (P1), resolved at merge:** `test_specs_index.py` counts 30 rows here and 30 there; the
second to merge makes it 31. `docs/CICD.md` exists only on #430's branch, so no block can edit it; once #430 is on
main, the implementing PR adds this line under its "Rollback and setup" section:
`Blue-green releases, promotion and abort: [BLUE_GREEN.md](BLUE_GREEN.md).`

**Red Hat's text and the operator's code disagree on one variable.** Red Hat's 1.21 document says of
`CLUSTER_SCOPED_ARGO_ROLLOUTS_NAMESPACES`: *"If this variable is not set, the RolloutManager manages rollouts only in the
namespace where it is deployed."* The upstream operator's code uses it as the list of namespaces allowed to *host* a
cluster-scoped RolloutManager, and refuses one elsewhere: *"namespace is not specified in
CLUSTER_SCOPED_ARGO_ROLLOUTS_NAMESPACES environment variable of Subscription resource"*
(argo-rollouts-manager `controllers/utils.go`, `allowedClusterScopedNamespace`). The lab's operator sets it to
`openshift-gitops` (§3.3). The guide follows the code: create the RolloutManager in a listed namespace.

## 1. The requirement

**In one sentence:** a release can run the new version beside the old one and switch readers only when a person says
so, without ever letting two versions write one database file.

The operator, 2026-09-27: *"adding argocd blue green using argo rollout … with a flag … My concern is the our db
migrations logic works well this option."* Then: *"We have deployed the rollout manager as part of our openshift
gitops helm"* and *"Group sync dashboard just consumes it."*

**Must not change** (issue #426):

- The default install stays a `Recreate` Deployment, with the migrations exactly as today. Proved: the default render
  and the lab's `crc.yaml` render are byte-identical to `22a485c`'s apart from the chart label (§6).
- No path ever runs two writers on one database file (§5).
- #305's refusal and #301's pre-upgrade copy stay: the store is not edited.
- The dashboard ServiceAccount loses no permission: the flag adds and removes no Role or binding (§6).
- PVCs are never removed: no template touches a claim.

## 2. Words

| Word | Meaning in this spec |
|---|---|
| blue | the version serving readers now |
| green | the new version, started beside blue |
| colour | one ReplicaSet's pods: blue or green (a Deployment's ReplicaSet is a colour too) |
| Rollout | Argo Rollouts' replacement for a Deployment, which adds the blue-green strategy |
| controller | the Argo Rollouts controller: the process that acts on Rollouts; a Rollout without it does nothing |
| RolloutManager | the OpenShift GitOps custom resource that installs the controller |
| active Service | the Service the Route points at; the controller adds the active colour's hash to its selector |
| preview Service | the Service the controller points at green before promotion, and at the active colour at rest |
| promotion | the switch: the controller moves the active Service's selector from blue to green |
| abort | stop before promotion: green is scaled down and the active Service stays on blue |
| undo | return to blue after promotion, by reverting the image in Git |
| `workloadRef` | a Rollout field that takes the pod template from an existing Deployment instead of carrying its own |
| template hash | `rollouts-pod-template-hash` on a Rollout's pods, `pod-template-hash` on a Deployment's: one value per ReplicaSet |
| copy | a `gsd-<UTC stamp>.db` the leader writes with `VACUUM INTO`: the report snapshot or the on-volume backup |
| seed | copy the newest copy into a colour's own database path before the dashboard opens it |
| migration | the schema change a new image applies to the database it opens (`gsd/store.py` `_migrate`) |
| expand/contract | changing a shared schema in two releases, so old and new code both work on it in between |

## 3. Read and measured

### 3.1 The repository at `22a485c`

| Fact | Source |
|---|---|
| One replica is `Recreate`, and `RollingUpdate` at one replica is refused, because both pods would open `/data/gsd.db` | charts/group-sync-dashboard/templates/deployment.yaml:15-17, :80 |
| The database path is `/data/gsd.db` at one replica and `/data/$(POD_NAME)/gsd.db` above one; `$(VAR)` resolves only against earlier env entries | deployment.yaml:149-177 |
| The data claim defaults to `ReadWriteMany`; reporting refuses any other mode | values.yaml:952; templates/_helpers.tpl:792 |
| A new image copies the database to `pre-upgrade/` beside it, then migrates, on open (#301) | local-development/gsd/store.py:1408, :1441-1444 |
| An older image refuses a newer database on open (#305) | store.py:1399-1405 |
| A replica that is not the lease holder polls nothing: "Standby: serve reads, write nothing" | local-development/gsd/poller.py:1275-1276 |
| But every replica flushes its readers' activity to its own store, leader or not | local-development/gsd/api.py:886-888; gsd/activity.py:186 |
| Backups and report snapshots are written by the leader only, after a poll, with `VACUUM INTO` under a `.tmp` name and renamed | poller.py:979-982, :1104, :1117-1120; store.py:1690-1768 |
| Defaults: a snapshot every 300 s into `/data/report` (keep 2), a backup every 6 h into `/data/backup` (keep 4) | gsd/config.py:829-830, :560; values.yaml:313-316 |
| The lease is 30 s, renewed every 10 s | local-development/gsd/leader.py:67-68 |
| The report service reads the newest snapshot, immutable, refuses a newer schema and accepts an older one | local-development/gsd/reporting/snapshot.py:112-117 |
| The Route points at the Service by name; the Service selects the pods by the selector labels; the ServiceMonitor selects Services by the same labels | templates/route.yaml:99-101; service.yaml:17; monitoring.yaml:22-23 |
| Readiness needs only a usable store, not a poll | gsd/api.py:3086-3098 |

### 3.2 Upstream and Red Hat documents

| Claim | Source (quoted) |
|---|---|
| Blue-green switches Service selectors | Argo Rollouts, [BlueGreen](https://argo-rollouts.readthedocs.io/en/stable/features/bluegreen/): "The rollout controller ensures proper traffic routing by injecting a unique hash of the ReplicaSet to these services' selectors." |
| At rest the preview Service points at the active ReplicaSet | same page, Sequence of Events 1: "a revision 1 ReplicaSet is pointed to by both the `activeService` and `previewService`" |
| The first ReplicaSet gets traffic at once | same page: "If the active service is not sending traffic to a ReplicaSet, the controller will immediately start sending traffic to the ReplicaSet." |
| `autoPromotionEnabled`, `scaleDownDelaySeconds`, `scaleDownDelayRevisionLimit` | same page: autoPromotionEnabled "Defaults to true"; scaleDownDelaySeconds "Defaults to 30"; scaleDownDelayRevisionLimit "limits the number of old active ReplicaSets to keep scaled up … If omitted, all ReplicaSets will be retained" |
| `abortScaleDownDelaySeconds` | [Rollout specification](https://argo-rollouts.readthedocs.io/en/stable/features/specification/): "Add a delay in second before scaling down the preview replicaset if update is aborted … Default is 30 second" |
| Abort leaves `spec.template` new; retry | [kubectl-argo-rollouts abort](https://argo-rollouts.readthedocs.io/en/stable/generated/kubectl-argo-rollouts/kubectl-argo-rollouts_abort/): "The previous ReplicaSet will be active. Note the 'spec.template' still represents the new rollout version. If the Rollout leaves the aborted state, it will try to go to the new version." |
| `workloadRef` and `scaleDown` | [Migrating](https://argo-rollouts.readthedocs.io/en/stable/migrating/): "`onsuccess`: the Deployment is scaled down after the Rollout becomes healthy"; "The Rollout won't try to manage existing Deployment Pods"; specification: "If the Rollout fails the Deployment will be scaled back up." |
| #4065 (open) | [argo-rollouts#4065](https://github.com/argoproj/argo-rollouts/issues/4065), "Rollout Creation with workloadRef Causes Service Downtime": on creation the new ReplicaSet's hash reaches both selectors at once (canary with Istio, 1.7.2). For blue-green it is the documented first-ReplicaSet behaviour above: a one-time wait, §4.3 m |
| #4681 (open) | [argo-rollouts#4681](https://github.com/argoproj/argo-rollouts/issues/4681): "`workloadRef.scaleDown: onsuccess` never scales down Deployment for blue-green with `postPromotionAnalysis`"; its Bug 2: "Hardcoded revision == 1 check prevents scaleDown on revision 2+" |
| Argo CD and Rollouts | Argo Rollouts [FAQ](https://argo-rollouts.readthedocs.io/en/stable/FAQ/): "if a Rollout created by Argo CD is paused, Argo CD detects that and marks the Application as suspended"; Argo CD's Rollout actions are abort, pause, promote-full, restart, resume, retry, skip-current-step (argo-cd `resource_customizations/argoproj.io/Rollout/actions`) |
| The controller does the work | Red Hat OpenShift GitOps 1.21, [Argo Rollouts](https://docs.redhat.com/en/documentation/red_hat_openshift_gitops/1.21/html-single/argo_rollouts/index) §1.2.1: "The controller reads all the rollout details and brings the cluster to the same state as described in the rollout definition." |
| What a RolloutManager installs | same, §1.2: "The Operator creates an argo-rollouts instance with the following namespace-scoped supporting resources: Argo Rollouts controller … metrics service … service account … roles … role bindings … secret"; the example is `spec: { }` |
| One mode per cluster | same, chapter 6: "To prevent unintended privilege escalation, Red Hat OpenShift GitOps allows only one mode of Argo Rollout installation at a time." Cluster-scoped is the default |
| The traffic plugin is for weights | same, §4.2: the OpenShift Routes plugin sets `spec.to.weight` and `alternateBackends` for a canary. Blue-green switches the Service selector and needs no plugin |
| GitOps 1.21 ships Argo Rollouts 1.9 | Red Hat OpenShift GitOps [1.21 release notes](https://docs.redhat.com/en/documentation/red_hat_openshift_gitops/1.21/html-single/release_notes/index), Table 1.1: 1.21.0 → Argo CD 3.4.3, Argo Rollouts 1.9.0. The table does not list 1.21.4's patch versions |
| A label as an environment variable | Kubernetes, [Downward API](https://kubernetes.io/docs/concepts/workloads/pods/downward-api/): "`metadata.labels['<KEY>']`: the text value of the pod's label named `<KEY>`" |

### 3.3 Measured on the lab, read-only (`oc get` only)

- `oc get rolloutmanagers.argoproj.io -A` → `No resources found`; `oc get rollouts.argoproj.io -A` → `No resources
  found`; no Deployment named like `rollout` in any namespace. The CRDs exist: `rollouts.argoproj.io`, `v1alpha1`,
  created `2026-09-19T01:11:47Z`, labels `olm.managed: true`, `operators.coreos.com/openshift-gitops-operator…`;
  its scale subresource reads `.spec.replicas` and `.status.selector`.
- The GitOps operator's CSV `openshift-gitops-operator.v1.21.4` sets `CLUSTER_SCOPED_ARGO_ROLLOUTS_NAMESPACES=
  openshift-gitops` and `ARGO_ROLLOUTS_IMAGE=registry.redhat.io/openshift-gitops-1/argo-rollouts-rhel9@sha256:0075fe90…`.
  The image's version label was not read (no registry credential here): the controller version on the lab is not
  measured beyond "1.21.x", which Red Hat lists with Argo Rollouts 1.9.
- RBAC: OLM aggregates `rollouts` create/update/patch/delete into `admin` and `edit`
  (`rollouts.argoproj.io-v1alpha1-admin`/`-edit`), and `oc auth can-i create rollouts.argoproj.io -n
  group-sync-dashboard --as=system:serviceaccount:openshift-gitops:openshift-gitops-argocd-application-controller`
  → `yes`. So a namespace admin (Helm) and the lab's Argo CD can create the Rollout.
- The release today: `group-sync-dashboard` Deployment, replicas 1, `Recreate`; the data claim
  `group-sync-dashboard-data` is `ReadWriteMany` (UID `f065b7a4-535c-4ef1-868c-58f5afee4953`), the artefacts claim
  `ReadWriteOnce` (UID `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`).

### 3.4 Measured hermetically, against `22a485c`'s store

| Question | Result |
|---|---|
| Does an open at the current schema write? | No. A second `Store()` on a schema-20 database: `total_changes` 0, file `417792` bytes, sha256 unchanged |
| Does an older image refuse a newer file? | Yes: `StoreSchemaTooNew: database schema 21 is newer than this dashboard understands (20)` |
| Can the seed script pick, verify and refuse? | Yes: `test_colour_seed_script.py`, ten cases of §4.3 e's table on real `VACUUM INTO` copies (§6) |

## 4. Design

### 4.1 The migration question

The problem in one line: blue-green runs two versions at once, and this store is one SQLite file that a new image
migrates on open and an older image refuses once migrated.

| Option | What the code does today | What would change | Failure modes | Verdict |
|---|---|---|---|---|
| (a) blue-green only for releases with no migration (#298 knows) | green on `/data/gsd.db` opens it; no migration means no schema change | a release-time switch between blue-green and Recreate | still two writers on one file: every replica flushes activity (api.py:886-888), and a WAL file shared across nodes on RWX "corrupts rather than errors" (deployment.yaml:16); the chart cannot see a migration at render time | refused: breaks "no two writers" |
| (b) green read-only until promotion, migrates at promotion | the store has no read-only mode; a new image cannot read an unmigrated schema | a read-only store across every write path, a promotion hook into the pod, and blue must stop before green migrates | blue writes blind to a migrated file during `scaleDownDelaySeconds`, which is what #305 exists to stop; the migration then runs after the switch, with readers on green | refused: most code, and it moves the migration after the switch |
| (c) expand/contract plus a "compatible newer schema" marker #305 accepts | #305 refuses any newer schema (store.py:1399-1405) | a compatibility field per migration, a relaxed #305, and a discipline on every future migration | still two writers on one file; a wrong marker lets old code write to a schema it does not understand | refused: breaks "no two writers", and weakens #305 |
| **(d) each colour its own database, seeded from the running colour's newest copy** | replicas above one already get their own file (deployment.yaml:164-175); the leader already writes consistent copies (store.py:1690-1768) | the database path names the colour; an init container seeds it | green starts from a copy up to 5 minutes old, and does not poll until blue stops (§4.4); disk for up to five colours | **chosen** |

**Why (d):** it is the only option where no path ever runs two writers on one file, and it needs no change to the
store: the new image migrates its own copy on open with #301's pre-upgrade copy, exactly as today, and blue never meets
the new schema, so a release never reaches #305's refusal; it still guards an undo whose directory was pruned
(§4.4 row 10). An abort needs no restore. It reuses two mechanisms that
exist: the per-replica path and the leader's `VACUUM INTO` copies.

### 4.2 The chart's shape: `workloadRef`, not a full Rollout template

| | A full Rollout template (the Deployment removed) | **`workloadRef`, `scaleDown: onsuccess` (the Deployment kept)** |
|---|---|---|
| Flag on, controller running | the Rollout starts its pods | the Rollout starts its pods beside the Deployment's; the controller scales the Deployment to 0 once the Rollout is healthy |
| **Flag on, no controller** | **outage**: Helm or Argo CD deletes the Deployment, and nothing creates pods for the inert Rollout | **the Deployment keeps serving**: only the controller scales it down ("scaled down after the Rollout becomes healthy") |
| The pod template | a second copy of 500 lines, or a large refactor into a helper | one: the Rollout reads the Deployment's |
| Known issues | — | #4681: `onsuccess` never fires with `postPromotionAnalysis` (not used here), and fires only on revision 1 (§4.4 row 6) |

`workloadRef` is chosen because it is the only shape that fails safe. Two consequences the templates carry:

1. The Deployment renders **no `replicas`** when the flag is on, so neither Helm nor Argo CD scales it back up after
   the controller scales it down. Kubernetes defaults a missing `replicas` to 1.
2. The Deployment's pod template is the Rollout's, so every colour's path is keyed by whichever template hash its pod
   carries: `/data/rs-$(ROLLOUTS_POD_TEMPLATE_HASH)$(POD_TEMPLATE_HASH)/gsd.db`. A missing label reads as empty
   (kubernetes `pkg/fieldpath/fieldpath.go` `ExtractFieldPathAsString` returns `accessor.GetLabels()[subscript]`), so a
   Rollout's pod is named by the first and a Deployment's by the second. Whether a Rollout's pod also carries
   `pod-template-hash` is not measured (§7 step 4 reads it); if it does, the two concatenated still name one ReplicaSet.

### 4.3 The design questions

| | Question | Answer | Why, and the source |
|---|---|---|---|
| a | The values | `rollout.enabled: false`, `rollout.strategy: blueGreen`, `rollout.autoPromotionEnabled: false`, `rollout.scaleDownDelaySeconds: 30` | Off: it needs a cluster prerequisite (the 0.14.0 rule, `test_values_defaults.py` KEPT_OFF). Manual promotion: the preview exists so a person checks green. 30 s is upstream's default |
| b | What renders with the flag on | the Deployment (no `replicas`, a seed init container, the colour path), a Rollout with `workloadRef`, a preview Service, the seed ConfigMap | §4.2. With the flag off nothing new renders: byte-identical (§6) |
| c | Where the migration runs | in green, on green's own copy, when the dashboard opens it, before the switch; #301's copy goes to `rs-<hash>/pre-upgrade/` | store.py:1408, :1441-1444, unchanged |
| d | What blue does meanwhile | serves the Route, holds the lease, polls, writes only its own file and the copies | poller.py:1275; green is not the lease holder until blue stops |
| e | How a colour gets its database | the `colour-seed` init container: missing file + a copy → seed, verified with `integrity_check`; empty volume → start empty; a database but no copy → refuse and retry; own file newer than every copy → keep; a newer copy of a schema the file has reached → set the directory aside and reseed; a newer copy of a newer schema → keep | `scripts/colour_seed.py`, standard library only, like `offsite_backup.py`; ten tests |
| f | Disk | keep its own directory and the four most recently written others | at most four others run at once: the active colour, one old active under `scaleDownDelayRevisionLimit: 1`, a replaced preview, and the Deployment's pod before the controller scales it to 0 |
| g | The abort | green is scaled down after `abortScaleDownDelaySeconds` (30); blue never saw green's schema; nothing to restore; finish by reverting Git; `retry` reseeds green from blue's newest copy (row e) | abort command doc (§3.2) |
| h | The undo after promotion | revert the image in Git; blue's ReplicaSet returns and seeds from the newest copy if its schema is one blue's file has reached, else keeps its own file | the second case equals restoring #301's copy today (`docs/RUNBOOK_backup_restore.md` §6), without the manual step |
| i | The Route | unchanged: it names the active Service, whose selector the controller moves | route.yaml:99-101; BlueGreen (§3.2) |
| j | A preview Route | none. Green is checked with `oc port-forward service/<release>-preview` and a bearer token | a browser login needs the Route the ServiceAccount's OAuth redirect reference names (route.yaml:76-81); a second Route would need a second reference and a second serving certificate |
| k | The RolloutManager | never rendered; the render requires the Rollout API and fails naming the prerequisite | Red Hat allows one mode per cluster (§3.2) and the lab's operator is cluster-scoped (§3.3); a namespace-scoped instance from this chart would fail there |
| l | **Flag on, no controller** | **the Deployment keeps serving**; the Rollout is inert; seen as `oc get rolloutmanagers.argoproj.io -A` empty and a Rollout with no status | §4.2; `test_the_deployment_still_serves_until_a_controller_makes_the_rollout_healthy`, `test_with_no_controller_the_route_still_reaches_the_deployments_pod` |
| m | The first switch | when the controller first sees the Rollout, the active Service moves to its first pod at once; readers wait for that pod's readiness, once | BlueGreen (§3.2); #4065 |
| n | The report service and its CronJobs | unchanged: a separate `Recreate` Deployment that rolls at the sync and reads the newest copy, blue's until green leads | snapshot.py:112-117 accepts an older copy |
| o | The traffic plugin | not needed | §3.2: it weights a canary; blue-green moves a selector |
| p | RBAC | the chart adds and removes no Role or binding; the controller gets its own from the operator; creating a Rollout needs `rollouts` create, aggregated into `admin` and `edit` | §3.3; `test_the_rollout_adds_no_rbac` |
| q | The preview Service's labels | not the selector labels | the ServiceMonitor selects Services by them (monitoring.yaml:22-23) and would scrape the preview too |
| r | Refused renders | no Rollout API; `replicaCount` ≠ 1; persistence off; a mode other than `ReadWriteMany`; leader election off; a strategy other than `blueGreen`; no copy source | `gsd.rolloutGuards`, the chart's `fail` pattern; seven parametrized tests |

### 4.4 Failure modes

| # | What happens | Effect | Seen as |
|---|---|---|---|
| 1 | Flag on, no controller | the Deployment serves; each Deployment upgrade seeds a new directory from the newest copy | no RolloutManager; the Rollout has no status |
| 2 | No copy yet, a database exists | the seed refuses; the kubelet retries the init container until the leader writes one (at most a poll plus 300 s) | `Init:CrashLoopBackOff`, `colour seed refused: a database exists … but no copy` |
| 3 | A corrupt copy | refused before it takes the name; nothing is left behind | the same init status, `failed integrity_check` |
| 4 | History between the copy and green's first poll | green records what changed since the copy as one change; a change made and undone in that window is only in blue's directory | expected; the preview should be short |
| 5 | Green's migration fails | green never becomes ready; the Rollout does not promote; blue serves | the dashboard log, as today |
| 6 | The first revision never became healthy (#4681 Bug 2) | the Deployment keeps one pod beside the Rollout's; separate files, one lease | `oc get deployments.apps <release>` READY 1/1 while the Rollout is Healthy; `docs/BLUE_GREEN.md` scales it to 0 once |
| 7 | Turning the flag off | the Deployment reopens `/data/gsd.db`, which lacks the history since the flag went on | `docs/BLUE_GREEN.md` "Turn it off": restore the active colour's copy first (runbook §4a) |
| 8 | An undo past a migration | blue returns on its own file; green's history stays in green's directory | the seed log names the newer copy it did not use |
| 9 | Clock skew between nodes larger than the gap between a colour's last write and the newest copy | a returning colour keeps its own file instead of reseeding | rare; the seed log says which it chose |
| 10 | An undo past a migration after blue's directory was pruned | blue seeds from green's newer copy and #305 refuses it: blue never becomes ready and green keeps serving | the dashboard log's `StoreSchemaTooNew`; restore #301's copy from green's `pre-upgrade/` into blue's directory (runbook §6), as today |

## 5. The guarantee

**No two versions open one database file.** Enforced by the path: each ReplicaSet's pods open `/data/rs-<its template
hash>/gsd.db`, so two colours have two files (`test_every_replicaset_opens_its_own_database_seeded_first`). The Deployment
and the Rollout are two ReplicaSets with two hashes. The flag-off path is today's single file under `Recreate`.

**Outside the guarantee, stated:**

1. Two pods of the **same** ReplicaSet can overlap when a pod is replaced (a drain): the ReplicaSet starts the
   replacement while the old pod terminates. This is today's behaviour for the Deployment too, unchanged; leader
   election and `busy_timeout` are the mitigations (values.yaml under `persistence`).
2. The seed reads a copy, never a live file; the copies are written by the lease holder, which is best-effort
   (values.yaml under `leaderElection`).
3. A person editing the Deployment or the Rollout by hand bypasses the render's refusals.

## 6. Tests, before and after

Three test files: two new, one edited. "Before" is `22a485c` with this spec plus §8's three test blocks only; "after"
is the same tree with every block applied. Where "before" fails only because a file is missing, the right-hand column
adds a run on the "after" tree with one rule switched off (a mutation), to show the test fails for the reason it names.

| Definition of Done | Test | Before | After |
|---|---|---|---|
| the flag is off by default and renders no Rollout | `test_chart_rollout.py::test_off_by_default_renders_no_rollout_object` | passed (nothing to render yet) | passed; FAILED when the flag-on branch keeps `replicas` (mutation M1) |
| no Rollout API: refused, naming the prerequisite | `test_without_the_crd_the_render_is_refused_and_names_the_prerequisite` | FAILED | passed |
| **flag on, no controller: the Deployment keeps serving** | `test_the_deployment_still_serves_until_a_controller_makes_the_rollout_healthy` | FAILED | passed; FAILED with `replicas` rendered (M1) and with `scaleDown: never` (M2) |
| **flag on, no controller: the Route still reaches the Deployment's pod** | `test_with_no_controller_the_route_still_reaches_the_deployments_pod` | FAILED | passed |
| one database per ReplicaSet, seeded first, env order | `test_every_replicaset_opens_its_own_database_seeded_first` | FAILED | passed; FAILED with `GSD_DB_PATH: /data/gsd.db` for every colour (M7) |
| the seed reads only the copies that are on | `test_the_seed_reads_only_the_copies_that_are_on` | FAILED | passed |
| the preview Service selects the pods and escapes the ServiceMonitor | `test_the_preview_service_selects_the_pods_and_escapes_the_servicemonitor` | FAILED | passed |
| the ConfigMap is the script, verbatim | `test_the_configmap_carries_the_script_verbatim` | FAILED | passed |
| manual promotion, one old colour | `test_the_rollout_keeps_one_old_colour_and_waits_for_a_person_by_default` | FAILED | passed |
| RBAC unchanged by the flag | `test_the_rollout_adds_no_rbac` | passed (the flag does not exist yet) | passed, with the Rollout rendered |
| the seven refusals | `test_an_unsafe_combination_is_refused[replicas\|rwop\|rwo\|no-persistence\|no-election\|canary\|no-seed-source]` | 7 FAILED | 7 passed |
| the seed: a new colour from the newest copy, verified | `test_colour_seed_script.py::test_a_new_colour_starts_from_the_newest_copy_verified` | ERROR (no script) | passed |
| newest by name across both directories | `test_the_newest_copy_is_chosen_by_name_across_both_directories` | ERROR | passed |
| an empty volume starts empty | `test_an_empty_volume_is_a_new_install` | ERROR | passed |
| a database without a copy is refused, never started empty | `test_a_database_without_a_copy_is_refused_never_started_empty` | ERROR | passed; FAILED when that case starts empty (M6) |
| a restart keeps its own file | `test_the_running_colour_keeps_its_own_file_on_a_restart` | ERROR | passed |
| a newer copy of the same schema reseeds, setting the file aside | `test_a_newer_copy_of_the_same_schema_replaces_the_file_and_sets_it_aside` | ERROR | passed |
| a retry after an abort reseeds from blue's older schema | `test_a_retry_after_an_abort_reseeds_from_the_older_schema` | ERROR | passed |
| an undo past a migration keeps its own file | `test_an_undo_past_a_migration_keeps_its_own_file` | ERROR | passed; FAILED without the schema check (M3) |
| a corrupt copy is refused and leaves nothing | `test_a_copy_that_fails_integrity_check_is_refused_and_leaves_nothing` | ERROR | passed; FAILED without `integrity_check` (M5) |
| prune keeps its own and four others | `test_prune_keeps_its_own_and_the_four_newest_other_colours` | ERROR | passed; FAILED with `--keep-others` 10 (M4) |
| the two new false defaults are stated exceptions | `test_values_defaults.py::test_the_only_false_defaults_are_the_stated_exceptions`, `::test_every_kept_off_boolean_has_a_reason_comment_above_it` | 2 FAILED (KEPT_OFF names keys values.yaml lacks) | passed |

Before, the three files: `17 failed, 7 passed, 10 errors`. After: `34 passed`. The mutations, each on a copy of the
applied tree: M1 `2 failed, 15 passed`, M2 `1 failed, 16 passed`, M3 `1 failed, 9 passed`, M4 `1 failed, 9 passed`,
M5 `1 failed, 9 passed`, M6 `1 failed, 9 passed`, M7 `1 failed, 16 passed`.

The gates, on the applied copy:

| Gate | Command | Result |
|---|---|---|
| the blocks | `apply-spec-blocks.py docs/specs/SPEC_W1_rollout_blue_green.md <copy>`, then `--apply`, on a fresh clone of `22a485c` + this spec | `19 blocks check out across 14 files`; the applied files are byte-equal to the proof tree's |
| the hermetic suite, main | `pytest -q --deselect tests/test_ui.py --deselect tests/test_live_smoke.py` on `22a485c` | `5453 passed, 19 skipped, 610 deselected` |
| the hermetic suite, after | the same, on the applied copy (with this spec and its index row) | `5484 passed, 19 skipped, 610 deselected` |
| the default render | `helm template group-sync-dashboard charts/group-sync-dashboard`, and again with `-f environments/crc.yaml`, against `22a485c` | 2922 and 3326 lines; 35 and 40 lines differ, each a `helm.sh/chart` label or the `checksum/config` that hashes the labelled ConfigMap; **0 lines** with `Chart.yaml` held at 0.59.2 |
| the render with the flag on | `helm template … -f environments/crc.yaml --api-versions argoproj.io/v1alpha1/Rollout --set rollout.enabled=true` | renders 2 Deployments (dashboard, report), 1 Rollout, 3 Services, 5 ConfigMaps |
| RBAC | Roles, ClusterRoles and bindings, `crc.yaml`, main against the flag on | 70 and 70; REMOVED 0, ADDED 0 |
| lint | `helm lint charts/group-sync-dashboard` (Helm v4.3.0), flag off and on | `1 chart(s) linted, 0 chart(s) failed` both; with the flag on lint cannot supply the Rollout API, and reports the refusal as `level=INFO msg="funcMap fail"` |
| the figure | `docs/diagrams/render.py … rollout-blue-green` | two PNGs written and read; `375 px viewport: scrollWidth 375` |
| Markdown | `markdownlint-cli2` on every edited `.md` | `docs/BLUE_GREEN.md`: 0 issues; the other three: 11 findings, as on `22a485c` |

## 7. On the lab, for the implementing pull request

Nothing here was run for this spec. **The walk's prerequisite is a running controller:** the lab has none (§3.3), and
ephico2real2/openshift-gitops-helm-chart#2 is where the operator's GitOps chart provides the RolloutManager. The
implementer runs this with the lab's kubeconfig, after review, and only when the operator gives the lab:

1. Record the UIDs of `group-sync-dashboard-data` and `group-sync-dashboard-report-artifacts`.
2. **Fail safe first:** with the prerequisite still absent, sync the chart with `rollout.enabled: true`. Expected: the
   Deployment's pod restarts once on `/data/rs-<its hash>/gsd.db` (its `colour-seed` log names the copy), the Route
   answers, `oc get rollouts.argoproj.io -n group-sync-dashboard group-sync-dashboard -o jsonpath='{.status}'` is empty.
3. The operator applies the RolloutManager (openshift-gitops-helm-chart#2). Check `oc get rolloutmanagers.argoproj.io -A`.
   Expected: the Rollout turns Healthy, the Deployment's `spec.replicas` becomes 0, and Argo CD stays Synced (the
   chart renders no `replicas`: not measured until then).
4. **A release with no migration:** move the image. Read green's labels
   (`oc get pods -n group-sync-dashboard -L rollouts-pod-template-hash,pod-template-hash`) and its `GSD_DB_PATH`.
   Expected: green seeds, no pre-upgrade copy is written, the Rollout
   pauses, `oc port-forward` + `/readyz` answers, `oc argo rollouts promote`, the active Service's selector takes
   green's hash, blue is scaled down 30 s later, green takes the lease.
5. **A release with a migration** (a branch with one migration): expected: `pre-upgrade copy written before migrating`
   in green's log under `/data/rs-<green>/pre-upgrade/`, blue's `rs-<blue>/gsd.db` still at the old schema
   (read with the runbook's §1 check), then promote.
6. **An abort:** a third release, `oc argo rollouts abort`. Expected: the active Service stays on blue, green is scaled
   down after 30 s, and blue's database is unchanged.
7. Record the PVC UIDs again; they must be unchanged. The evidence goes under `reports/<date>_<slug>/`.

## 8. Implementation blocks

Nineteen blocks over fourteen files, in apply order: the seed script, the templates, the values, the chart's version,
the docs and the figure's page, the tests. Lines added / removed per file (§6's proof tree): `colour_seed.py` +151,
`_helpers.tpl` +58, `deployment.yaml` +43, `rollout.yaml` +63, `values.yaml` +16, `Chart.yaml` +2 −1, the chart
README +2, `docs/BLUE_GREEN.md` +261, `docs/diagrams/rollout-blue-green/source.html` +252, `docs/README.md` +1, the
CHANGELOG +6, `test_colour_seed_script.py` +164, `test_chart_rollout.py` +142, `test_values_defaults.py` +2.

The figure's PNGs cannot be blocks. With the blocks applied, render them from the repository root and read both
before committing:

    local-development/.venv/bin/python docs/diagrams/render.py docs/diagrams/rollout-blue-green/source.html docs/diagrams/rollout-blue-green rollout-blue-green

It exits non-zero on a page error, a font that did not load, a name/figure mismatch, or sideways scroll at 375 px.

<!-- block: charts/group-sync-dashboard/scripts/colour_seed.py | create -->
```python
#!/usr/bin/env python3
"""Give a blue-green colour its own database before the dashboard opens it. Standard library only.

With `rollout.enabled` every ReplicaSet of the Rollout (a colour: blue is the running one, green the new
one) opens its OWN file, /data/rs-<rollouts-pod-template-hash>/gsd.db, so two versions never write one
SQLite file (docs/BLUE_GREEN.md). This script runs as the pod's init container, before the dashboard
starts, and decides which database the colour starts from:

  1. its own file is missing, and a copy exists       -> copy the newest copy in, verified;
  2. its own file is missing, no copy, no database    -> nothing: a new install starts empty;
  3. its own file is missing, no copy, a database     -> refuse, exit 1: the kubelet retries until the
                                                         running colour's leader has written a copy;
  4. its own file exists, and the newest copy is newer and of a schema its own file has reached
                                                      -> set its own directory aside, copy the newest in
                                                         (a retry after an abort, or an undo with no
                                                         migration: the newer history wins);
  5. its own file exists, otherwise                   -> keep it (a restart of the running colour, or an
                                                         undo past a migration its image cannot read).

"A copy" is a `gsd-<UTC stamp>.db` the running colour's leader wrote with VACUUM INTO: the report
snapshot (/data/report, every reporting.snapshot.intervalSeconds) or the on-volume backup
(config.backup.dir). Newest by name across both: the stamp is UTC with microseconds.

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


class SeedError(Exception):
    """A start this script refuses. Exits 1 with the reason; the kubelet retries the init container."""


def copy_time(path: Path) -> float:
    """The UTC instant in a copy's name, gsd-20260927T101500.123456Z.db, as epoch seconds."""
    stamp = path.name[len("gsd-"):-len(".db")]
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
    print(f"seeded {db} from {copy} ({db.stat().st_size} bytes, schema {schema(db, immutable=True)})")


def prune(data: Path, own: Path, keep_others: int) -> None:
    others = sorted((d for d in data.glob(COLOUR_PREFIX + "*") if d.is_dir() and d != own),
                    key=last_write, reverse=True)
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
        prune(data, own, args.keep_others)
    except (SeedError, sqlite3.Error, OSError, ValueError) as exc:
        print(f"colour seed refused: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

<!-- block: charts/group-sync-dashboard/templates/_helpers.tpl | edit -->
```yaml

{{- define "gsd.reportName" -}}
```

```yaml

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

{{- /* The combinations under which two colours could share a database, or a colour could not start. */ -}}
{{- define "gsd.rolloutGuards" -}}
{{- if eq (include "gsd.rolloutEnabled" .) "true" -}}
{{- if not (.Capabilities.APIVersions.Has "argoproj.io/v1alpha1/Rollout") -}}
{{- fail "rollout.enabled=true needs the Argo Rollouts CRD (argoproj.io/v1alpha1 Rollout), and this cluster does not serve it. The controller is a cluster prerequisite this chart never creates: one cluster-scoped RolloutManager from the cluster's OpenShift GitOps installation (docs/BLUE_GREEN.md, \"Before you start\"; https://docs.redhat.com/en/documentation/red_hat_openshift_gitops/1.21/html-single/argo_rollouts/index). Under helm template, pass --api-versions argoproj.io/v1alpha1/Rollout." -}}
{{- end -}}
{{- if ne (toString .Values.rollout.strategy) "blueGreen" -}}
{{- fail (printf "rollout.strategy must be blueGreen; got %q. A canary would send some readers to each version, and each version keeps its own history." (toString .Values.rollout.strategy)) -}}
{{- end -}}
{{- if ne (int .Values.replicaCount) 1 -}}
{{- fail "rollout.enabled=true requires replicaCount 1. Blue-green already runs a second pod during a release; above one replica every pod keeps its own history (templates/deployment.yaml, PER-POD database file)." -}}
{{- end -}}
{{- if not .Values.persistence.enabled -}}
{{- fail "rollout.enabled=true requires persistence.enabled=true: green seeds its database from a copy on the data claim, and an emptyDir has none." -}}
{{- end -}}
{{- if ne (include "gsd.accessMode" .) "ReadWriteMany" -}}
{{- fail (printf "rollout.enabled=true requires persistence.accessMode=ReadWriteMany; got %s. Blue and green run at once: ReadWriteOncePod admits one pod, and ReadWriteOnce leaves green unable to attach the claim on another node." (include "gsd.accessMode" .)) -}}
{{- end -}}
{{- if not .Values.leaderElection.enabled -}}
{{- fail "rollout.enabled=true requires leaderElection.enabled=true: blue and green run at once, and only the lease holder may poll and write copies." -}}
{{- end -}}
{{- if not (include "gsd.seedSources" .) -}}
{{- fail "rollout.enabled=true needs a copy for green to start from: reporting.enabled (a snapshot every reporting.snapshot.intervalSeconds) or config.backup.enabled with config.backup.dir under /data/." -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "gsd.reportName" -}}
```

<!-- block: charts/group-sync-dashboard/templates/deployment.yaml | edit -->
```yaml
spec:
  replicas: {{ .Values.replicaCount }}
  strategy:
```

```yaml
spec:
  {{- if eq (include "gsd.rolloutEnabled" .) "true" }}
  # No replicas: the Rollout controller scales this Deployment to 0 once the Rollout is healthy; without one it serves on.
  {{- else }}
  replicas: {{ .Values.replicaCount }}
  {{- end }}
  strategy:
```

<!-- block: charts/group-sync-dashboard/templates/deployment.yaml | edit -->
```yaml
        checksum/config: {{ include (print $.Template.BasePath "/configmap.yaml") . | sha256sum }}
        {{- with .Values.podAnnotations }}{{- toYaml . | nindent 8 }}{{- end }}
```

```yaml
        checksum/config: {{ include (print $.Template.BasePath "/configmap.yaml") . | sha256sum }}
        {{- if eq (include "gsd.rolloutEnabled" .) "true" }}
        checksum/colour-seed: {{ .Files.Get "scripts/colour_seed.py" | sha256sum }}
        {{- end }}
        {{- with .Values.podAnnotations }}{{- toYaml . | nindent 8 }}{{- end }}
```

<!-- block: charts/group-sync-dashboard/templates/deployment.yaml | edit -->
```yaml
      priorityClassName: {{ . | quote }}
      {{- end }}
```

```yaml
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
```

<!-- block: charts/group-sync-dashboard/templates/deployment.yaml | edit -->
```yaml
                  fieldPath: metadata.name
            - name: GSD_DB_PATH
```

```yaml
                  fieldPath: metadata.name
            {{- if eq (include "gsd.rolloutEnabled" .) "true" }}
            {{- include "gsd.colourEnv" . | nindent 12 }}
            {{- else }}
            - name: GSD_DB_PATH
```

<!-- block: charts/group-sync-dashboard/templates/deployment.yaml | edit -->
```yaml
              {{- end }}
            # Through the helper, not the raw value: an unrecognised level does not degrade to a
```

```yaml
              {{- end }}
            {{- end }}
            # Through the helper, not the raw value: an unrecognised level does not degrade to a
```

<!-- block: charts/group-sync-dashboard/templates/deployment.yaml | edit -->
```yaml
            name: {{ include "gsd.fullname" . }}-curlrc
        {{- if .Values.trustedCA.injected.enabled }}
```

```yaml
            name: {{ include "gsd.fullname" . }}-curlrc
        {{- if eq (include "gsd.rolloutEnabled" .) "true" }}
        - name: colour-seed
          configMap:
            name: {{ include "gsd.fullname" . }}-colour-seed
        {{- end }}
        {{- if .Values.trustedCA.injected.enabled }}
```

<!-- block: charts/group-sync-dashboard/templates/rollout.yaml | create -->
```yaml
{{- include "gsd.rolloutGuards" . }}
{{- if eq (include "gsd.rolloutEnabled" .) "true" }}
# Blue-green with Argo Rollouts (docs/BLUE_GREEN.md). The Rollout takes its pods from the Deployment (workloadRef),
# so the pod template has one source, and the Deployment keeps serving until the Rollout is healthy: a cluster
# with the CRD but no running controller leaves this object inert and the dashboard up.
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
      autoPromotionEnabled: {{ .Values.rollout.autoPromotionEnabled }}
      scaleDownDelaySeconds: {{ int .Values.rollout.scaleDownDelaySeconds }}
      # One old colour in its scale-down delay at most, so colour_seed.py's --keep-others 4 never prunes a running one.
      scaleDownDelayRevisionLimit: 1
---
# Green before promotion; the running colour at rest. Reached with `oc port-forward` and a bearer token, not a
# Route: an OAuth login needs the Route the ServiceAccount's redirect reference names (docs/BLUE_GREEN.md).
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

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->
```yaml
strategy: ""

```

```yaml
strategy: ""

# Blue-green with Argo Rollouts (docs/BLUE_GREEN.md). OFF by default: it needs the cluster's Argo Rollouts
# controller, a RolloutManager the cluster's OpenShift GitOps installation provides; this chart never creates one.
# On, templates/deployment.yaml renders a Rollout instead of the Deployment, and each version (a colour) opens
# its OWN database, /data/rs-<rollouts-pod-template-hash>/gsd.db, seeded from the running colour's newest copy
# (charts/group-sync-dashboard/scripts/colour_seed.py). So green migrates its own copy before the switch and
# blue never meets a newer schema. Refused with replicaCount > 1, a claim other than ReadWriteMany, persistence
# or leaderElection off, strategy set, or no copy to seed from (reporting and config.backup both off).
rollout:
  enabled: false
  # blueGreen is the only strategy: canary would send some requests to each colour's own history.
  strategy: blueGreen
  # false: the Rollout pauses with green on the preview Service until a person promotes it.
  autoPromotionEnabled: false
  # How long blue keeps running after the switch; Argo Rollouts' default, for the Service change to propagate.
  scaleDownDelaySeconds: 30

```

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->
```yaml
# shared fleet login account safe (#383).
version: 0.59.2
# 0.8.0 (2026-09-03). A Users tab — every user with a synced membership, filtered as you type on
```

```yaml
# shared fleet login account safe (#383).
# CHART 0.60.0 (2026-09-27), MINOR: rollout.enabled, blue-green with Argo Rollouts (#426, SPEC_W1), off by default.
version: 0.60.0
# 0.8.0 (2026-09-03). A Users tab — every user with a synced membership, filtered as you type on
```

<!-- block: charts/group-sync-dashboard/README.md | edit -->
```markdown
| `leaderElection.enabled` | `true` | only the lease holder polls. **Best-effort, not a write fence** — see [Leader election](#leader-election). Must be `false` above one replica; the chart refuses to render otherwise |
| `leaderElection.leaseName` | `group-sync-dashboard` | the `coordination.k8s.io` Lease object's name, in the release namespace. Two releases in one namespace must not share it |
```

```markdown
| `leaderElection.enabled` | `true` | only the lease holder polls. **Best-effort, not a write fence** — see [Leader election](#leader-election). Must be `false` above one replica; the chart refuses to render otherwise |
| `rollout.enabled` | `false` | blue-green with Argo Rollouts; needs the cluster's Rollouts controller, which this chart never creates. Each version opens its own database, so the migration runs on green's copy before the switch. See [docs/BLUE_GREEN.md](../../docs/BLUE_GREEN.md) |
| `rollout.autoPromotionEnabled` / `.scaleDownDelaySeconds` | `false` / `30` | `false`: the Rollout waits for a person to promote green. Blue keeps running this long after the switch |
| `leaderElection.leaseName` | `group-sync-dashboard` | the `coordination.k8s.io` Lease object's name, in the release namespace. Two releases in one namespace must not share it |
```

<!-- block: docs/BLUE_GREEN.md | create -->
```markdown
# Blue-green releases with Argo Rollouts

This page is for the person who turns blue-green on, promotes a release, aborts one, or turns it off again.
The switch is `rollout.enabled` in the chart. It is **off by default**, and off the chart installs exactly
what it installed before.

**The rule behind it:** blue and green never open the same database file. Each version has its own copy.
Green starts from blue's newest copy and upgrades that copy before any reader reaches green. Blue keeps
serving on its own file the whole time.

## The short version

1. A new image reaches Git. Argo CD syncs it.
2. The Argo Rollouts controller starts green beside blue. Blue keeps serving.
3. Green copies blue's newest database copy into its own directory, then upgrades it (the migration).
4. The Rollout pauses. You check green through the preview Service.
5. You promote. The active Service moves to green. The Route does not change.
6. Blue stops 30 seconds later. Its directory stays on the volume, for an undo.

If you abort at step 4 instead, green stops and blue carries on untouched. There is nothing to restore.

## Words used on this page

| Word | Meaning here |
|---|---|
| blue | the version serving readers now |
| green | the new version, started beside blue |
| colour | one version's pods: one ReplicaSet of the Rollout (or of the Deployment) |
| Rollout | the Argo Rollouts object that runs blue and green; the chart renders it when `rollout.enabled` is true |
| active Service | the Service the Route sends readers to (`<release>`); the controller points it at one colour |
| preview Service | a second Service (`<release>-preview`) the controller points at green before the switch |
| promotion | the switch: the controller moves the active Service from blue to green |
| abort | stop a release before promotion: green is scaled down and the active Service stays on blue |
| undo | go back to blue after promotion, by reverting the image in Git |
| copy | a `gsd-<time>.db` file the running colour's leader writes: the report snapshot or the backup |
| migration | the schema upgrade a new image runs on the database it opens (`gsd/store.py`) |
| expand/contract | a way to change a shared database so old and new code both work on it; this chart does not need it, because the colours never share one |
| RolloutManager | the OpenShift GitOps object that installs the Argo Rollouts controller; one per cluster |

## The picture

<!-- markdownlint-disable MD033 -->
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="diagrams/rollout-blue-green/rollout-blue-green.dark.png">
  <source media="(prefers-color-scheme: light)" srcset="diagrams/rollout-blue-green/rollout-blue-green.light.png">
  <img alt="Green copies blue's newest database copy into its own directory and migrates it while blue serves; promotion moves the active Service to green; an abort leaves blue untouched; with no controller the Deployment keeps serving" src="diagrams/rollout-blue-green/rollout-blue-green.light.png">
</picture>
<!-- markdownlint-enable MD033 -->

*Figure 1. Seven lanes, time flowing down. The migration runs in green, on green's own copy, before the switch;
blue never meets the new schema. An abort (red) leaves blue as it was. An undo (grey) brings blue back on the
newest copy it can read, or on its own file. The dashed box is a cluster prerequisite, not part of this chart;
everything else drawn ships with `rollout.enabled`.*

````text
GIT/ARGO CD      CONTROLLER          ROUTE/SERVICES     BLUE                GREEN                DATA /data           REPORT
                 [prerequisite]      Route->active      serves, leader  --writes--> rs-blue/gsd.db   reads newest copy
                 absent? Rollout     active->blue       polls                        report/ 5 min <--
                 inert, Deployment   preview->blue                                   backup/ 6 h
                 serves  [red]
new image  --->  sees template                                                                     report Deployment
syncs Deploy-    creates green  ---> preview->green                     1 colour-seed <--newest copy-- rolls at once,
ment template                                                             to rs-green/            reads blue's copy
                                                        meanwhile blue: 2 #301 copy, migrate
                                                        serves, writes    green's copy --> rs-green/
                                                        rs-blue/ only   3 ready, no lease
                 paused: a person
                 checks preview   --abort [red]-------------------------> green down after 30 s;
                   |                                                      blue never migrated
                 promote -------> active->green     30 s later blue    green serves, lease, --> copies --> reads green's
                                  Route unchanged   scaled to 0,       writes copies
                                                    rs-blue/ kept
undo: revert  --[grey]------------------------------> blue returns on the newest copy it can read, else its own rs-blue/
````

## Before you start: the controller

A Rollout is only a description. **The Argo Rollouts controller does the work**: it creates green, switches the
Services and scales blue down. Red Hat: *"The controller reads all the rollout details and brings the cluster to the
same state as described in the rollout definition."* Without it, nothing happens.

The controller is a cluster prerequisite. **This chart never creates it.** The cluster's OpenShift GitOps
installation provides one cluster-scoped RolloutManager (for example the operator's `openshift-gitops` chart,
ephico2real2/openshift-gitops-helm-chart#2). It is shared by every team's Rollouts on the cluster.

Check that it runs:

````sh
oc get rolloutmanagers.argoproj.io -A          # one, Phase Available
oc get customresourcedefinitions.apiextensions.k8s.io rollouts.argoproj.io
````

For a cluster without one, this is Red Hat's minimal RolloutManager. The cluster owner creates it once, in a
namespace the GitOps operator allows to host a cluster-scoped instance: the operator's
`CLUSTER_SCOPED_ARGO_ROLLOUTS_NAMESPACES` setting lists them (on the reference cluster, `openshift-gitops`).

````yaml
apiVersion: argoproj.io/v1alpha1
kind: RolloutManager
metadata:
  name: argo-rollout
  namespace: openshift-gitops
spec: {}
````

Red Hat allows one mode per cluster: cluster-scoped (the default) or namespace-scoped. A cluster running the
namespace-scoped mode (`NAMESPACE_SCOPED_ARGO_ROLLOUTS=true` on the operator) needs a namespace-scoped
RolloutManager in the release namespace instead. That is the cluster owner's choice; this chart creates neither.

## Turn it on

````yaml
rollout:
  enabled: true
````

The chart refuses to render, with the reason, when:

| Setting | Why it is refused |
|---|---|
| the cluster does not serve `argoproj.io/v1alpha1` Rollout | the Rollout kind does not exist there (with the kind and no controller, see "When there is no controller") |
| `replicaCount` is not 1 | each extra replica keeps its own history already |
| `persistence.enabled: false` | green seeds from a copy on the data claim |
| `persistence.accessMode` is not `ReadWriteMany` | blue and green run at once; `ReadWriteOncePod` admits one pod, `ReadWriteOnce` one node |
| `leaderElection.enabled: false` | only the lease holder may poll and write copies |
| `rollout.strategy` is not `blueGreen` | a canary would split readers across two histories |
| `reporting.enabled` and `config.backup.enabled` both off | green has no copy to start from |

What changes when it is on:

- The Deployment stays, with the same pod template and no `replicas` field. The Rollout reads its template from
  it (`workloadRef`) and scales it to 0 once the Rollout is healthy.
- Each colour's database is `/data/rs-<hash>/gsd.db`, where `<hash>` is its ReplicaSet's template hash. An init
  container, `colour-seed`, prepares it before the dashboard starts.
- A preview Service, `<release>-preview`, and a ConfigMap holding the seed script.

**The first switch.** The first time the controller sees the Rollout, it points the active Service at the
Rollout's first pod straight away (Argo Rollouts, "BlueGreen"). Readers wait until that pod is ready, a few
seconds, once. After that every release is a blue-green release.

## A release, step by step

1. Merge the new image. Argo CD syncs the Deployment's template. The Deployment has 0 pods, so nothing starts from
   it; the controller sees the change and creates green.
2. The report service and its CronJobs are a separate Deployment. They roll at once, and read blue's copies until
   green takes over: an older copy is accepted, a newer one refused.
3. Watch green start:

   ````sh
   oc argo rollouts get rollout <release> -n <namespace> --watch
   oc logs -n <namespace> <green pod> -c colour-seed
   ````

   The seed log names the copy it used, for example `seeded /data/rs-<hash>/gsd.db from /data/report/gsd-….db`.
   The dashboard's log then shows the pre-upgrade copy and each migration.
4. The Rollout pauses (`autoPromotionEnabled: false`). Argo CD shows the Application as Suspended.

## Check green before promoting

The preview Service has no Route. A browser login needs the Route the ServiceAccount's OAuth redirect names, so
check green over the API with your token:

````sh
oc port-forward -n <namespace> service/<release>-preview 8443:8080
curl -sk https://localhost:8443/readyz
curl -sk -H "Authorization: Bearer $(oc whoami -t)" https://localhost:8443/api/version
````

## Promote

````sh
oc argo rollouts promote <release> -n <namespace>
````

Or the Rollout's **Resume** action in Argo CD. The active Service moves to green. Blue stops after
`rollout.scaleDownDelaySeconds` (30). Green takes the lease within 30 seconds after that, then polls and writes the
copies the report service reads.

## Abort, and retry

````sh
oc argo rollouts abort <release> -n <namespace>
````

The active Service stays on blue. Green is scaled down after 30 seconds. **Nothing to restore**: blue never saw
green's schema. Green's directory stays on the volume until the prune removes it.

Abort does not change Git: the Rollout still wants the new image. Finish by reverting the image in Git.
`oc argo rollouts retry rollout <release>` tries green again: it starts from blue's newest copy, not from its
aborted one.

## Undo after the switch

Revert the image in Git. Blue starts again as the new green, and its `colour-seed` decides its database:

| Case | Blue starts on |
|---|---|
| no migration between blue and green | the newest copy: green's history is kept |
| green migrated the schema | blue's own file, as it was when blue stopped; the history since stays in green's directory |

The second row is what a restore of the pre-upgrade copy gives today (`docs/RUNBOOK_backup_restore.md` §6), done
for you. If blue's directory was already pruned (four newer colours ago), blue can only start from green's newer
copy, which it refuses (`StoreSchemaTooNew`); green keeps serving. Restore green's pre-upgrade copy into blue's
directory with the runbook's §6.

## When there is no controller

With the flag on and no controller, the Rollout is inert. **The Deployment keeps serving**, because only the
controller scales it down. You see:

- `oc get rolloutmanagers.argoproj.io -A` prints nothing;
- `oc get rollouts.argoproj.io -n <namespace> <release> -o jsonpath='{.status}'` is empty;
- the dashboard pod belongs to the Deployment, and its database is `/data/rs-<the Deployment's hash>/gsd.db`.

Each Deployment upgrade then starts from the newest copy, like a new colour. Install the controller, and the next
sync starts the Rollout.

## The Deployment still has a pod after the Rollout is healthy

The controller scales the Deployment to 0 only when the Rollout's **first** revision becomes healthy (Argo Rollouts
issue #4681). If that first revision failed and a later one succeeded, the Deployment's pod keeps running beside
the Rollout's. They never share a database, but only one of them holds the lease and polls. Scale it down once;
the chart renders no `replicas`, so it stays down:

````sh
oc get deployments.apps -n <namespace> <release>      # READY 1/1 while the Rollout is Healthy
oc scale deployments.apps -n <namespace> <release> --replicas=0
````

## Turn it off

With the flag off, the Deployment opens `/data/gsd.db` again, the file it had before the flag went on. That file
does not have the history recorded since. Before turning it off:

1. Pause the Rollout's Argo CD sync, then scale the Rollout to 0.
2. Restore the active colour's newest copy into `/data/gsd.db` with `docs/RUNBOOK_backup_restore.md` §4a.
3. Set `rollout.enabled: false` and sync.

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

Then it keeps its own directory and the four most recently written others, and removes the rest.

**What it costs:**

- **History between the copy and the switch.** Green starts from a copy up to `reporting.snapshot.intervalSeconds`
  old (5 minutes), or `config.backup.intervalHours` (6) with reporting off. Green does not poll until blue stops.
  Its first poll then records what changed since the copy as one change. A change made and undone in that window
  is only in blue's directory.
- **Disk.** Up to five colour directories, each about the database's size with its pre-upgrade copies, on
  `persistence.size`.
```

<!-- block: docs/diagrams/rollout-blue-green/source.html | create -->
```html
<title>Blue-Green Rollout</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>
:root {
  --ground: #f5f6f8; --surface: #ffffff; --ink: #18212c; --muted: #58636f; --rule: #d7dce3; --lane: #f0f2f5;
  --argo: #0e6f68; --ctl: #6a44b0; --data: #a55a0b; --data-wash: #fbf1e4;
  --blue: #2457a8; --blue-wash: #e6eefb; --green: #2c7a3f; --green-wash: #e5f4e8;
  --gap: #b3261e; --gap-wash: #fbe9e7;
  --font-body: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, "SF Mono", Menlo, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --ground: #0e131a; --surface: #151c25; --ink: #e5e9ef; --muted: #9aa5b3; --rule: #2a3440; --lane: #111821;
    --argo: #3fcfc0; --ctl: #b79cf0; --data: #f0a53c; --data-wash: #2a2014;
    --blue: #7fa9f0; --blue-wash: #16223a; --green: #74cf8a; --green-wash: #14281a;
    --gap: #f2857c; --gap-wash: #2d1614;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --ground: #0e131a; --surface: #151c25; --ink: #e5e9ef; --muted: #9aa5b3; --rule: #2a3440; --lane: #111821;
  --argo: #3fcfc0; --ctl: #b79cf0; --data: #f0a53c; --data-wash: #2a2014;
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
      <svg viewBox="0 0 1120 950" role="img" aria-label="Seven lanes, time flowing down: Git and Argo CD, the Argo Rollouts controller, the Route and Services, blue, green, the data claim, and the report service. At rest the Route reaches blue through the active Service, and blue's leader writes copies of its database that the report service reads. A new image in Git changes the Deployment's template; the controller creates green and points the preview Service at it. Green's init container copies blue's newest copy into its own directory; the dashboard then takes the pre-upgrade copy and migrates green's copy, while blue keeps serving and writing its own file. The Rollout pauses until a person promotes it. An abort scales green down and leaves blue untouched, so nothing is restored. Promotion moves the active Service to green; blue is scaled down after 30 seconds and its directory is kept; green takes the lease and writes the copies the report service reads. An undo brings blue back on the newest copy it can read, or its own file. With no controller the Rollout is inert and the Deployment keeps serving. The controller is a cluster prerequisite, not shipped by the chart.">
        <defs>
          <marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="currentColor"/></marker>
          <marker id="ah-argo" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="var(--argo)"/></marker>
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
          <text x="80" y="24">GIT · ARGO CD</text>
          <text x="240" y="24">ROLLOUTS CONTROLLER</text>
          <text x="400" y="24">ROUTE · SERVICES</text>
          <text x="560" y="24" fill="var(--blue)">BLUE · RUNNING</text>
          <text x="720" y="24" fill="var(--green)">GREEN · NEW</text>
          <text x="880" y="24">DATA CLAIM /data</text>
          <text x="1040" y="24">REPORT · CRONJOBS</text>
        </g>
        <g font-family="IBM Plex Sans, sans-serif" font-size="10.5" fill="var(--muted)" text-anchor="middle">
          <text x="240" y="40">openshift-gitops</text>
          <text x="720" y="40">release namespace: 3–7</text>
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
          <rect x="8" y="210" width="144" height="66" rx="6" fill="var(--surface)" stroke="var(--argo)" stroke-width="1.5"/>
          <text x="80" y="228" font-weight="600" fill="var(--argo)">new image in Git</text>
          <text x="80" y="244">Argo CD syncs the</text>
          <text x="80" y="259">Deployment's template</text>
          <text x="80" y="272" font-size="10.5" fill="var(--muted)">0 pods: none start</text>
          <rect x="168" y="210" width="144" height="64" rx="6" fill="var(--surface)" stroke="var(--ctl)" stroke-width="1.5"/>
          <text x="240" y="228" font-weight="600" fill="var(--ctl)">sees the template</text>
          <text x="240" y="244">(workloadRef),</text>
          <text x="240" y="260">creates green</text>
          <line x1="152" y1="232" x2="164" y2="232" stroke="var(--argo)" stroke-width="1.5" marker-end="url(#ah-argo)"/>
          <path d="M80,276 L80,302 L964,302" stroke="var(--argo)" stroke-width="1.5" fill="none" marker-end="url(#ah-argo)"/>
          <text x="560" y="296" fill="var(--argo)" font-size="10.5">the report Deployment rolls at once</text>
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
          <text x="240" y="610">a person checks the</text>
          <text x="240" y="626">preview, then decides</text>
          <line x1="240" y1="274" x2="240" y2="572" stroke="var(--ctl)" stroke-width="1.5" marker-end="url(#ah-ctl)"/>
          <text x="246" y="430" text-anchor="start" fill="var(--ctl)" font-size="10.5">green ready</text>
          <path d="M312,608 L644,608" stroke="var(--gap)" stroke-width="1" fill="none" marker-end="url(#ah-gap)"/>
          <text x="478" y="602" fill="var(--gap)" font-size="10.5">abort</text>
          <rect x="648" y="572" width="144" height="90" rx="6" fill="var(--gap-wash)" stroke="var(--gap)" stroke-width="1"/>
          <text x="720" y="590" font-weight="600" fill="var(--gap)">green scaled down</text>
          <text x="720" y="606" fill="var(--gap)">after 30 s; rs-green/</text>
          <text x="720" y="622" fill="var(--gap)">stays until pruned.</text>
          <text x="720" y="638" fill="var(--gap)">Blue never migrated:</text>
          <text x="720" y="652" fill="var(--gap)" font-size="10.5">nothing to restore</text>

          <!-- the switch -->
          <rect x="168" y="690" width="144" height="46" rx="6" fill="var(--surface)" stroke="var(--ctl)" stroke-width="2"/>
          <text x="240" y="709" font-weight="700" fill="var(--ctl)">promote</text>
          <text x="240" y="725">the switch</text>
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
          <text x="720" y="720">lease within 30 s:</text>
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
          <text x="80" y="819">undo: revert the</text>
          <text x="80" y="835">image in Git</text>
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
          <line x1="660" y1="820" x2="690" y2="820" stroke="var(--argo)" stroke-width="1.5"/><text x="698" y="824">Argo CD applies Git</text>
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

<!-- block: docs/README.md | edit -->
```markdown
- [RUNBOOK_backup_restore.md](RUNBOOK_backup_restore.md) — back up and restore the dashboard's history.

```

```markdown
- [RUNBOOK_backup_restore.md](RUNBOOK_backup_restore.md) — back up and restore the dashboard's history.
- [BLUE_GREEN.md](BLUE_GREEN.md) — blue-green releases with Argo Rollouts: turn it on and off, promote, abort, undo.

```

<!-- block: docs/CHANGELOG.md | edit -->
```markdown
## Unreleased

```

```markdown
## Unreleased

- **Blue-green releases with Argo Rollouts, off by default (#426, SPEC_W1, chart 0.60.0).** `rollout.enabled`
  renders a Rollout that takes its pods from the Deployment (`workloadRef`, `scaleDown: onsuccess`), a preview
  Service and a seed script. Each version opens its own database, seeded from the running version's newest copy,
  so the migration runs on green's copy before the switch. With no Rollouts controller the Deployment keeps
  serving. `docs/BLUE_GREEN.md` is the guide. The default render is unchanged apart from the chart label.

```

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
```

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
    ({"replicaCount": "2", "leaderElection__enabled": "false", "reporting__enabled": "false"}, "replicaCount 1"),
    ({"persistence__accessMode": "ReadWriteOncePod", "reporting__enabled": "false"}, "ReadWriteMany"),
    ({"persistence__accessMode": "ReadWriteOnce", "reporting__enabled": "false"}, "ReadWriteMany"),
    ({"persistence__enabled": "false", "reporting__enabled": "false"}, "persistence.enabled=true"),
    ({"leaderElection__enabled": "false"}, "leaderElection.enabled=true"),
    ({"rollout__strategy": "canary"}, "must be blueGreen"),
    ({"reporting__enabled": "false", "config__backup__enabled": "false"}, "a copy for green to start from"),
], ids=["replicas", "rwop", "rwo", "no-persistence", "no-election", "canary", "no-seed-source"])
def test_an_unsafe_combination_is_refused(values, reason):
    ok, out = render(rollout__enabled="true", **values)
    assert not ok
    assert reason in out
```

<!-- block: local-development/tests/test_values_defaults.py | edit -->
```python
    "clusterConfig.secrets.writes.enabled": "S2 (#230): a write path on Secrets widens the dashboard's read-only posture; off until the operator turns it on — default pending the operator's A/B call of 2026-09-20; B flips the default and removes this exception",
}
```

```python
    "clusterConfig.secrets.writes.enabled": "S2 (#230): a write path on Secrets widens the dashboard's read-only posture; off until the operator turns it on — default pending the operator's A/B call of 2026-09-20; B flips the default and removes this exception",
    "rollout.enabled": "W1 (#426): needs the cluster's Argo Rollouts controller, a RolloutManager this chart never creates",
    "rollout.autoPromotionEnabled": "W1 (#426): the preview exists so a person checks green before the switch",
}
```
