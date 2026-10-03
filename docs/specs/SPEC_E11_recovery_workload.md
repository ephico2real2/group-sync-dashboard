# SPEC E11 — recovery mode as its own workload (#532)

| | |
|---|---|
| Programme | none: the follow-up to Epic E (#385), the operator's direction of 2026-10-02 on #532 |
| Batch | none: the follow-up to Epic E (#385), the operator's direction of 2026-10-02 on #532 |
| Release | — (post-programme; rides the next chart release) |
| Version on release | chart 0.65.0 (chart only) |
| Version note | The blocks touch `charts/`, `docs/`, `local-development/restore-db.sh`, `local-development/restore-db.py` and `local-development/tests/`. `restore-db.sh` and `restore-db.py` run on the operator's laptop and stream into the pod (`local-development/restore-db.sh#in_pod`); neither is a `COPY` source, and neither is in `publish.yml`'s `on.push.paths`, so no image is built and there is no app bump. Next free chart MINOR under SPEC_E5's version rule: G4 claims 0.62.1 and 0.62.2, G3 0.62.3, W1 0.63.0, G2 0.64.0 |
| Issue | [#532](https://github.com/ephico2real2/group-sync-dashboard/issues/532) |
| Status | released |
| Source | OB1-lite's research and specification of 2026-10-02, written before any code from #532's body and its three comments (the second is the operator's settled direction). Measured on main `a3394ba5` (application 3.1.0, chart 0.62.0) with helm v4 and Python 3.14; upstream source read raw at Argo CD `v3.4.7` (the lab's) and Kubernetes `v1.35.0` (the lab runs v1.35.6); the CRC lab (OpenShift 4.22.7) read with `oc get` only. §7's blocks were proved on a throwaway tree of `a3394ba5` (§4.3) |

## How to read this spec

**The point in one sentence: the chart renders recovery mode as a second Deployment, `<fullname>-recovery`, on every
release at 0 replicas, and `recovery.enabled: true` only swaps the two Deployments' `replicas` (app 1 → 0, recovery
0 → 1), so both are Healthy to Argo CD, nothing is retried, turning recovery off takes one sync whatever `prune`
says, and a required pod anti-affinity makes the scheduler keep the two pods off the database at the same time.**

Today (#303) recovery mode is the app's own Deployment with a different command and a readiness probe that can never
pass. Argo CD waits for that Deployment to be healthy, it never is, the sync fails at the progress deadline and is
retried, and the change that turns recovery off waits behind the retries: 12 min 49 s on the lab (#532's body). §2
shows from Argo CD's source why, and from the Kubernetes scheduler's source why the new ordering holds. §2a lists the
alternatives. §3 is the design with its safety budget. §4 is the tests (T532-1 to T532-9). §5 is the lab walk the
implementing pull request runs. §6 is what an operator sees. §7 is the whole change as implementation blocks
(`docs/specs/README.md`, "Implementation blocks"), applied with

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_E11_recovery_workload.md . --apply

## Orchestrator's notes

1. **The recovery Deployment is rendered on every release, at 0 replicas when off (decided, "easy to manage, best
   practice").** The operator's direction says turning recovery off "takes effect within one sync". If the recovery
   Deployment were rendered only while on, turning it off would delete it, and deletion under Argo CD is `prune`:
   automated sync prunes only with `prune: true`, and with `prune: false` (Argo CD's default) the recovery pod would
   keep running, the app pod would wait behind the anti-affinity (§3.3) and the app's Deployment would reach its
   progress deadline and be retried, which is #532 again. Rendered always, the switch is two `replicas` fields and
   no object is created or deleted (T532-1). The cost is one idle Deployment (0/0) and one ConfigMap holding
   `recovery_mode.py` in every release. This changes #303's "the default render has no extra object"
   (`charts/group-sync-dashboard/templates/recovery.yaml`'s old comment, T303-14); the safety guarantees of #303 are
   kept.
2. **The ordering is the scheduler's, not a script's (decided).** The candidates the mandate named, and why they are
   not used, are in §2a. A required pod anti-affinity needs no RBAC, no image change and no code; the scheduler
   enforces it in both directions (§2.4), and it holds on any storage, which a lock file does not.
3. **The anti-affinity's topology key is `kubernetes.io/os` (decided, with one condition stated).** A required
   anti-affinity on `kubernetes.io/hostname` keeps the pods off the same node only, and the default claim is
   ReadWriteMany (the lab's is, §2.6), so two nodes could both mount it. `kubernetes.io/os` has the value `linux` on
   every node this image can run on, so the domain is the cluster. The Kubernetes docs say the
   `LimitPodHardAntiAffinityTopology` admission controller, when enabled, limits a required anti-affinity's
   `topologyKey` to `kubernetes.io/hostname`; it is not enabled on the lab (§2.6). **Open question for the operator:**
   do production clusters enable that admission plugin? If any does, the recovery pod is refused at admission there,
   and the fallback is the pod-list init container of §2a, which needs `list` on `pods` in the namespace for the
   dashboard ServiceAccount (an RBAC addition, the operator's call).
4. **The break glass simplifies, and stays the incident path.** With the recovery Deployment always rendered, §4d's
   hand edit is `oc scale` of the two Deployments (no `helm pull`, no ConfigMap, no patch), and step 6 has nothing to
   remove: Argo CD's self-heal puts the two `replicas` back. Step 7 (terminate a retrying operation) stays for a
   release still on a chart before 0.65.0.
5. **The two misleading `restore-db.sh` messages (#532's third comment, SPEC_E10's walk O1) are corrected** in
   `restore-db.py`: the `--list` note on an unmounted `/offsite` names the pod's mount, and the closing line after a
   restore names both ways back, the values file and §4d step 5 (T532-8). Under the new break glass the pod is the
   chart's own recovery pod, so the offsite claim is mounted exactly when the values file says.
6. **Index, at implementation time:** the four specified specs whose versions sit between the tree and this one (G4
   0.62.1/0.62.2, G3 0.62.3, W1 0.63.0, G2 0.64.0) keep their versions here. If this spec ships before them,
   `Chart.yaml` reaches 0.65.0 and `tests/test_specs_index.py::test_a_spec_the_changelog_has_not_begun_names_versions_the_tree_has_not_reached`
   fails on their rows (measured on the applied tree, §4.3), so the implementing pull request moves their planned
   versions above 0.65.0 in their headers and index rows, as #542's did for the same four. Those blocks are not
   written here because they depend on which ships first.
7. **A long release name:** the recovery pod's `app` label is `<fullname>-recovery`. A `fullname` longer than 54
   characters makes it longer than a label value may be (63), and the API server refuses the Deployment by name.
   The chart's `-recovery` ConfigMap already appends the same suffix; no guard is added.
8. **Correction from the §5 walk (2026-10-03): each pod names the other in its OWN anti-affinity (chart 0.65.1).**
   §2.4's claim that "a waiting pod is retried when the blocking pod is deleted" holds only when the deleted pod
   matches the waiting pod's own anti-affinity; I retract it as stated.
   - **The source.** kube-scheduler v1.35.0, `pkg/scheduler/framework/plugins/interpodaffinity/plugin.go` L223–231
     (`isSchedulableAfterPodChange`): on a delete it returns `Queue` only if the deleted pod matches the waiting pod's
     `antiTerms`, which come from the waiting pod's own `Affinity`. `filtering.go` L188–190 (`podMatchesAllAffinityTerms`)
     returns false for no terms. So an app pod with no anti-affinity of its own is skipped, and waits for the
     unschedulable flush, `DefaultPodMaxInUnschedulablePodsDuration = 5 * time.Minute`
     (`pkg/scheduler/backend/queue/scheduling_queue.go` L66).
   - **Measured on the lab, chart 0.65.0.** Recovery off was one sync with `retryCount` absent, Argo CD's operation
     01:51:48Z → 01:57:27Z. The recovery pod was killed at 01:52:04Z, and the app pod was refused at 01:52:04Z
     ("didn't satisfy existing pods anti-affinity rules"). The app pod was not scheduled until 01:57:07Z, **303 s**
     later. In the other direction, the recovery pod carries its own term: it was refused at 01:57:28Z and scheduled
     at 01:57:30Z, 2 s later.
   - **The fix, the operator's decision of 2026-10-03.** The app pod carries the mirror term: a required
     anti-affinity against `gsd.recoverySelectorLabels`, on `kubernetes.io/os`. The recovery pod's delete then matches
     the app pod's own term, and the app pod is re-queued at once.
   - **The trade-off, accepted.** The app pod itself now depends on `LimitPodHardAntiAffinityTopology` being off.
     The operator, 2026-10-03, knows of no production cluster that enables it (note 3's open question, answered).
   - **The change.** The template's one block becomes symmetric:

     ```yaml
     {{- $affinity := deepCopy (.Values.affinity | default dict) }}
     {{- $other := ternary (include "gsd.selectorLabels" .) (include "gsd.recoverySelectorLabels" .) $recovery }}
     {{- $anti := $affinity.podAntiAffinity | default dict }}
     {{- $term := dict "labelSelector" (dict "matchLabels" ($other | fromYaml)) "topologyKey" "kubernetes.io/os" }}
     {{- $_ := set $anti "requiredDuringSchedulingIgnoredDuringExecution" (append ($anti.requiredDuringSchedulingIgnoredDuringExecution | default list) $term) }}
     {{- $_ := set $affinity "podAntiAffinity" $anti }}
     ```

     T532-3 now pins both terms. The app's pod template changes once, so the upgrade to 0.65.1 rolls the app pod once.

## 1. The mandate, and what is out of scope

From #532's body and the operator's direction (#532, second comment, settled):

- With `recovery.enabled: true`, the main Deployment renders `replicas: 0` (Healthy to Argo CD); a separate recovery
  template renders the recovery pod, with its own labels, so the dashboard Service never selects it and its
  readiness no longer has to fail; both workloads are Healthy; `recovery.enabled: false` takes effect within one
  sync.
- Same namespace, same ServiceAccount, same SCC, no `runAsUser`, no custom SCC (the operator's UID measurements are
  in #532's second comment). The dashboard ServiceAccount's RBAC is not reduced: rendered RBAC diff, REMOVED 0.
- Values-file-first: the switch stays `recovery.enabled`; no sync waves, hooks or Application fields as the
  mechanism.
- The recovery pod must never run while an app pod still has the database open, by the chart alone.
- Every consumer of today's recovery pod follows: `restore-db.sh`, SPEC_E5's offsite mount (and the offsite Job's
  co-location), SPEC_E6's card, the runbook's §4 and §4d, the PodDisruptionBudget, and the tests.
- The two misleading `restore-db.sh` messages from SPEC_E10's walk (O1).

Out of scope: the recovery script itself (`charts/group-sync-dashboard/scripts/recovery_mode.py`, unchanged), the
restore logic in `restore-db.py` (only its selection and two messages change), and any change to Argo CD's
Application or ApplicationSet.

**Must not change (#532's body):** recovery mode's guarantees (#303: one pod, the writer stopped, the TTL as the
bound, no liveness kill mid-restore), the values-file-only path, and the dashboard ServiceAccount's permissions.

**SPEC_E6's KPI card and SPEC_H1's routes:** both run in the app, which is stopped in recovery mode; neither reads
the recovery pod (`grep -rn 'GSD_RECOVERY' local-development/gsd` finds nothing, §2.7). Nothing changes for them.

## 2. Research, measured

### 2.1 Argo CD's health of a Deployment (the Deployment at 0 and the recovery Deployment)

`gitops-engine/pkg/health/health_deployment.go` at Argo CD `v3.4.7` (fetched raw 2026-10-02 with
`curl -s https://raw.githubusercontent.com/argoproj/argo-cd/v3.4.7/gitops-engine/pkg/health/health_deployment.go | nl -ba`;
identical lines 28–70 on `argoproj/gitops-engine` master):

```
    36		if deployment.Generation <= deployment.Status.ObservedGeneration {
    39			case cond != nil && cond.Reason == "ProgressDeadlineExceeded":
    41					Status:  HealthStatusDegraded,
    44			case deployment.Spec.Replicas != nil && deployment.Status.UpdatedReplicas < *deployment.Spec.Replicas:
    49			case deployment.Status.Replicas > deployment.Status.UpdatedReplicas:
    54			case deployment.Status.AvailableReplicas < deployment.Status.UpdatedReplicas:
    67		return &HealthStatus{
    68			Status: HealthStatusHealthy,
```

Settles: a Deployment at `replicas: 0` whose old pod is gone has `UpdatedReplicas` 0 ≥ 0, `Replicas` 0, and
`AvailableReplicas` 0 ≥ 0, so it is Healthy. The recovery Deployment is Healthy once its one pod is available,
which a container with no readiness probe is as soon as it runs. Today's recovery Deployment stays at line 54
(available 0 < updated 1), then reaches line 39 at the progress deadline: Degraded.

### 2.2 Why today's retry happens: the operation waits for health, a Degraded resource fails it

`gitops-engine/pkg/sync/sync_context.go` at `v3.4.7`:

```
   545					switch healthStatus.Status {
   546					case health.HealthStatusHealthy:
   547						sc.setResourceResult(task, task.syncStatus, common.OperationSucceeded, healthStatus.Message)
   548					case health.HealthStatusDegraded:
   549						sc.setResourceResult(task, task.syncStatus, common.OperationFailed, healthStatus.Message)
   559		multiStep := tasks.multiStep()
   560		runningTasks := tasks.Filter(func(t *syncTask) bool { return (multiStep || t.isHook()) && t.running() })
```

and `gitops-engine/pkg/sync/sync_tasks.go` line 275: `return s.wave() != s.lastWave() || s.phase() != s.lastPhase()`.
The chart has hooks and more than one phase, so the sync is multi-step and the operation stays Running while the
Deployment is Progressing, and fails when it turns Degraded. `controller/appcontroller.go` at `v3.4.7`:

```
  1579			if !terminating && (state.RetryCount < state.Operation.Retry.Limit || state.Operation.Retry.Limit < 0) {
  1587					state.Phase = synccommon.OperationRunning
  1590					state.Message = fmt.Sprintf("%s. Retrying attempt #%d at %s.", state.Message, state.RetryCount, retryAt.Format(time.Kitchen))
  2241		if app.Operation != nil {
  2242			logCtx.Infof("Skipping auto-sync: another operation is in progress")
```

Settles the 12 min 49 s: a failed operation is put back to Running and retried up to `limit` (line 1579), and while
an operation exists the automated sync of the new revision is skipped (line 2241). The lab's policy
`{limit:3, backoff 30s×2, max 5m}` (§2.6) with a 600 s progress deadline is the measured delay. With both
Deployments Healthy (§2.1) the operation succeeds, nothing is retried, and the next revision syncs at once.

### 2.3 The scheduler's inter-pod anti-affinity, and terminating pods

The Kubernetes docs, `content/en/docs/concepts/scheduling-eviction/assign-pod-node.md` (kubernetes/website `main`,
fetched raw 2026-10-02), lines 243–246: *"Inter-pod affinity and anti-affinity take the form "this Pod should (or, in
the case of anti-affinity, should not) run in an X if that X is already running one or more Pods that meet rule Y",
where X is a topology domain like node, rack, cloud provider zone or region, or similar"*; lines 355–364: *"In
principle, the `topologyKey` can be any allowed label key"* and *"For `requiredDuringSchedulingIgnoredDuringExecution`
Pod anti-affinity rules, the admission controller `LimitPodHardAntiAffinityTopology` limits `topologyKey` to
`kubernetes.io/hostname`."*

`pkg/scheduler/framework/plugins/interpodaffinity/filtering.go` at Kubernetes `v1.35.0`:

```
    37		ErrReasonExistingAntiAffinityRulesNotMatch = "node(s) didn't satisfy existing pods anti-affinity rules"
   352	func satisfyExistingPodsAntiAffinity(state *preFilterState, nodeInfo fwk.NodeInfo) bool {
   358				if state.existingAntiAffinityCounts[tp] > 0 {
   412	func (pl *InterPodAffinity) Filter(ctx context.Context, cycleState fwk.CycleState, pod *v1.Pod, nodeInfo fwk.NodeInfo) *fwk.Status {
   428			return fwk.NewStatus(fwk.Unschedulable, ErrReasonExistingAntiAffinityRulesNotMatch)
```

Settles the symmetry: an incoming pod is also refused a node when an EXISTING pod's required anti-affinity matches
it, so one term on the recovery pod holds the app pod back too. The file has no `DeletionTimestamp` check
(`grep -c -i deletiontimestamp` → 0), while `podtopologyspread/common.go` line 152 skips terminating pods
(`if p.GetPod().DeletionTimestamp != nil ...`): inter-pod anti-affinity counts a terminating pod. The scheduler's
cache drops a pod only on its delete event, `pkg/scheduler/eventhandlers.go` line 462
(`sched.Cache.RemovePod(logger, pod)`); an update, a deletion timestamp included, is `sched.Cache.UpdatePod` at line
425. A pod object is deleted only after the kubelet has stopped its containers (graceful deletion). And
`interpodaffinity/plugin.go` line 101 registers `fwk.Add | fwk.UpdatePodLabel | fwk.Delete` on pods, with line 223
*"Pod is deleted. Return Queue when the deleted pod matching the target pod's anti-affinity."*: the waiting pod is
retried as soon as the blocking pod is gone.

### 2.4 This repository (main `a3394ba5`)

- Today's recovery mode is a branch of the app's Deployment: `charts/group-sync-dashboard/templates/deployment.yaml#RECOVERY MODE (#303)`
  swaps the command, and `charts/group-sync-dashboard/templates/deployment.yaml#a readiness probe that cannot pass`
  keeps it out of the Service. The pod carries `gsd.selectorLabels`
  (`charts/group-sync-dashboard/templates/_helpers.tpl#define "gsd.selectorLabels"`: `app.kubernetes.io/name`,
  `app.kubernetes.io/instance`, `app: <fullname>`), which the Service, the PodDisruptionBudget
  (`charts/group-sync-dashboard/templates/pdb.yaml#gsd.selectorLabels`), the ServiceMonitor, the report
  NetworkPolicy and the offsite Job's pod affinity (`charts/group-sync-dashboard/templates/backup-offsite.yaml#ReadWriteOnce binds the data claim to one NODE`)
  select on.
- `restore-db.sh` lists `oc get pods -l "app=${REL}"` (`local-development/restore-db.sh#preflight`) and
  `restore-db.py`'s preflight requires exactly one pod with `GSD_RECOVERY_MODE=true` in its dashboard container's
  env (`local-development/restore-db.py#preflight`).
- The two messages of O1, both in `local-development/restore-db.py`: the `list` note "is not mounted (recovery mode
  mounts the offsite claim only when backup.offsite uses its pvc destination)", and the closing line "restored. Set
  recovery.enabled: false in this release's values file …".
- The image already runs any UID OpenShift assigns: the operator's measurements on #532 (namespace range
  `1000790000/10000`, the pod at `uid 1000790000`, `gid 0`, `/data` `2775` group 0). The recovery Deployment keeps
  `serviceAccountName` and `podSecurityContext`, so it gets the same SCC and UID (T532-4).

### 2.5 Measured on this repository with the change applied (§4.3's tree)

```
$ helm template t <main chart> ... ; helm template t <applied chart> ...   # default values
added: [('ConfigMap', 't-group-sync-dashboard-recovery'), ('Deployment', 't-group-sync-dashboard-recovery')] removed: []
changed: []
RBAC objects 17 17 lines 464 464 REMOVED 0 ADDED 0
$ diff <(helm template ... ) <(helm template ... --set recovery.enabled=true)       # applied chart
2294c2294
<   replicas: 1
---
>   replicas: 0
2635c2635
<   replicas: 0
---
>   replicas: 1
```

The app's Deployment renders exactly as on main; the switch is two lines; the RBAC render is identical.

### 2.6 Measured on the CRC lab, read-only (2026-10-02)

```
$ oc get pvc -n group-sync-dashboard -o custom-columns=NAME:.metadata.name,MODES:.spec.accessModes,SC:.spec.storageClassName,UID:.metadata.uid
group-sync-dashboard-backup-offsite     [ReadWriteOnce]   crc-csi-hostpath-provisioner   7f505595-db2e-40be-a4ee-c6ed271c42b6
group-sync-dashboard-data               [ReadWriteMany]   crc-csi-hostpath-provisioner   f065b7a4-535c-4ef1-868c-58f5afee4953
group-sync-dashboard-report-artifacts   [ReadWriteOnce]   crc-csi-hostpath-provisioner   08c7d45c-a3eb-47be-8506-f24ea7a3e0e3
$ oc get application.argoproj.io -n openshift-gitops -o jsonpath=...   # the dashboard's Application
group-sync-dashboard {"automated":{"prune":true,"selfHeal":true},"retry":{"backoff":{"duration":"30s","factor":2,"maxDuration":"5m"},"limit":3},"syncOptions":["CreateNamespace=true","RespectIgnoreDifferences=true","ServerSideApply=true"]}
$ oc get deploy -n group-sync-dashboard -o custom-columns=NAME:.metadata.name,REPLICAS:.spec.replicas,GRACE:.spec.template.spec.terminationGracePeriodSeconds,PDS:.spec.progressDeadlineSeconds
group-sync-dashboard                     1          30      600
$ oc version | grep -i 'server\|kubernetes'
Server Version: 4.22.7
Kubernetes Version: v1.35.6
$ oc get nodes -L kubernetes.io/os --no-headers
crc   Ready   control-plane,master,worker   65d   v1.35.6   linux
$ oc get cm config -n openshift-kube-apiserver -o jsonpath='{.data.config\.yaml}' | python3 -c '... admission plugins containing "Affinity"'
enabled: []  disabled: []  pluginConfig keys with Affinity: []
[] 45          # 45 enable-admission-plugins, none of them LimitPodHardAntiAffinityTopology
```

Settles: the data claim is ReadWriteMany (two pods can mount it at once, so the ordering must be enforced, not
inferred from the access mode); the app pod's grace period is 30 s, well inside the 600 s progress deadline the
recovery Deployment has to wait in; the lab admits a required anti-affinity on `kubernetes.io/os`.

### 2.7 Every consumer of today's recovery pod

| Consumer | What it reads | Change |
|---|---|---|
| `restore-db.sh` / `restore-db.py` | pods by `app=<release>`; `GSD_RECOVERY_MODE` in the dashboard container | lists `app in (<release>,<release>-recovery)`; the env check is unchanged (T532-7) |
| SPEC_E5's offsite mount | `$offsiteClaim`, computed only when recovery is on | computed always; mounted in the recovery pod only (T303 offsite tests) |
| The offsite Job on ReadWriteOnce | pod affinity to `gsd.selectorLabels` | matches the app's pod or the recovery pod (T532-5) |
| SPEC_E6's KPI card, SPEC_H1's routes | nothing of the recovery pod; they run in the app, stopped in recovery mode | none |
| Runbook §4, §4d | `-l app=$REL`, `deploy/$REL`, the hand patch | `app=$REL-recovery`, `deploy/$REL-recovery`, two `oc scale` (T532-9) |
| PodDisruptionBudget | `gsd.selectorLabels` | unchanged; selects the app's pods only (T532-2) |
| Tests rendering recovery mode | the app's Deployment | the recovery Deployment by name (§7) |

## 2a. Alternatives considered

| Option | Source | Cost here | Decision |
|---|---|---|---|
| Keep one Deployment; let the runbook state the delay | #532's body; SPEC_E10 | 12 min 49 s with the app down on every recovery under Argo CD; the operator rejected it on #532 | rejected |
| Make the failing readiness probe pass (recovery pod Ready) on the app's Deployment | §2.1 | the Service selects the pod, readers reach a proxy with no upstream | rejected |
| A separate recovery Deployment rendered only while on | the operator's direction | turning off is a prune; with `prune: false` the app never returns (Orchestrator's notes, 1) | rejected |
| A separate recovery Deployment rendered always, `replicas` as the switch | §2.1, §2.5 | one idle Deployment and one ConfigMap per release | **chosen** |
| A Job or bare Pod as the recovery template | Argo CD's Job/Pod health (`gitops-engine/pkg/health/health.go` lines 108–140 map Deployment and Pod kinds) | a bare Pod is not re-created after eviction and cannot be "scaled off" without deleting it (prune again); a Job completes, the TTL crash-loop becomes a failed Job | rejected |
| Ordering: Argo CD sync waves or hooks | Argo CD docs | Argo-specific, forbidden as the mechanism (the operator's rule of 2026-10-01) | rejected |
| Ordering: an init container waiting on a lock file the app holds (`flock`) | Linux `flock(2)` | the app must take the lock (an image change), and a lock on a network filesystem is only as good as the client's lock support | rejected |
| Ordering: SQLite's own locking | SQLite file locking | the app opens and closes connections; an unlocked moment is not "the app is gone"; a restore replaces the file | rejected |
| Ordering: the app's shutdown removing a marker | — | a SIGKILL or a node loss leaves the marker, and the recovery pod waits for ever or needs a timeout that guesses | rejected |
| Ordering: an init container reading the pod list | the Kubernetes API | needs `list` on `pods` for the dashboard ServiceAccount (new RBAC) and code in the chart | the fallback of Orchestrator's notes 3 only |
| Ordering: required pod anti-affinity, `topologyKey: kubernetes.io/os` | §2.3 | none at run time; refused where `LimitPodHardAntiAffinityTopology` is enabled (not on the lab) | **chosen** |
| Same anti-affinity on `kubernetes.io/hostname` | §2.3 | keeps the pods off one node only; the lab's claim is ReadWriteMany | rejected |

**Reconciliation.** Research says a Deployment at 0 replicas is Healthy (§2.1, line 67): the app's Deployment
renders `replicas: 0` in recovery mode at `charts/group-sync-dashboard/templates/deployment.yaml#The app's Deployment at 0 is Healthy`.
Research says a Degraded resource fails a multi-step operation and a failed operation is retried (§2.2): the
recovery Deployment carries no probe that can fail, at
`charts/group-sync-dashboard/templates/deployment.yaml#No readiness probe in the recovery workload`. Research says
a required anti-affinity is enforced against existing and terminating pods in both directions (§2.3): the term is
at `charts/group-sync-dashboard/templates/deployment.yaml#THE ORDERING ON THE DATA CLAIM`, selecting
`gsd.selectorLabels`. Research says a Service selects pods by label (the recovery pod must not match): the
recovery pod's labels are `charts/group-sync-dashboard/templates/_helpers.tpl#define "gsd.recoverySelectorLabels"`,
whose `app` differs. Research says an automated sync without `prune` leaves a removed object: the switch is
`replicas` at `charts/group-sync-dashboard/templates/deployment.yaml#ternary 1 0 $recoveryOn`, and nothing is
removed.

## 3. The design

### 3.1 Two Deployments from one pod spec

`deployment.yaml` renders its Deployment twice, in a `range` over `app` and `recovery`, with `{{- with $ }}` so the
pod spec below is the one file it is today. `$recoveryOn` is the switch (`gsd.recoveryEnabled`); inside the range,
`$recovery` is "this is the recovery workload", so every existing `{{- if $recovery }}` branch (command, env,
mounts, volumes, no liveness probe) now applies to the recovery Deployment only, and the app's Deployment renders
exactly as on main (§2.5).

| | app (`<fullname>`) | recovery (`<fullname>-recovery`) |
|---|---|---|
| `replicas`, recovery off | `replicaCount` | 0 |
| `replicas`, recovery on | 0 | 1 |
| selector and pod labels | `gsd.selectorLabels` | `gsd.recoverySelectorLabels` (`app: <fullname>-recovery`, `component: recovery`) |
| command | uvicorn | `recovery_mode.py` |
| liveness / readiness | as configured | none / none |
| affinity | `affinity` from values | `affinity` from values plus the anti-affinity term |
| ServiceAccount, security contexts, volumes, sidecar | the chart's | the same, plus `recovery-script` and `offsite` |

Why: one pod spec means no drift between the two; `replicas` as the only switch means nothing is created or deleted
when it flips.

```
recovery.enabled: false            recovery.enabled: true
  Deployment <fullname>   1/1        Deployment <fullname>            0/0  Healthy
  Deployment <fn>-recovery 0/0       Deployment <fn>-recovery         1/1  Healthy
  Service -> app pod                 Service -> no endpoint (recovery pod not selected)
                                     scheduler: recovery pod Pending until the app pod object is gone
```

### 3.2 The guards stay where they were

`recovery.enabled=true` still requires `replicaCount: 1`, `persistence.enabled: true` and a positive `recovery.ttl`
(T303-5, T303-6, T303-7, unchanged). The offsite claim is computed whatever the switch, because the recovery
Deployment is rendered whatever the switch.

### 3.3 The safety property, as a budget over the system

**Property:** at most one of {an app pod, the recovery pod} of one release has its containers running at any
moment, so at most one process tree can hold `gsd.db`. **Budget: 0 overlapping seconds**, for every pair of pods
of the release's two Deployments in its namespace, across every rollout, scale, eviction and node drain, on any
storage class and access mode. **Scope:** pods created by the chart's two Deployments and scheduled by the
default scheduler, on nodes labelled `kubernetes.io/os` (every node the image runs on). **Outside the scope, named:**
a `--force --grace-period=0` delete (the API object goes before the kubelet has stopped the containers), a pod bound
by hand with `spec.nodeName` (bypasses the scheduler), a second scheduler, and a cluster with
`LimitPodHardAntiAffinityTopology` enabled (the recovery pod is refused, so the property holds by having no
recovery pod; Orchestrator's notes 3).

**Why it holds:** the recovery pod's required anti-affinity matches the app's selector labels in the domain of all
`linux` nodes; the scheduler refuses the recovery pod while any matching pod is in its cache, and its cache holds a
pod until the API object is deleted (§2.3), which is after the kubelet has stopped the containers. The same term
refuses an incoming app pod while the recovery pod exists (§2.3, existing pods' anti-affinity). Each pod is
re-queued when the blocking pod's delete event arrives.

**The wait is bounded:** by the outgoing pod's `terminationGracePeriodSeconds` (30 s on the lab) plus the kubelet's
stop, against the Deployment's 600 s progress deadline (§2.6). A pod stuck terminating on a lost node holds the
other workload back until the node is resolved; that is the safe direction.

### 3.4 The way back

`recovery.enabled: false` scales the recovery Deployment to 0 and the app's back to `replicaCount` in one apply.
The recovery pod receives SIGTERM (`recovery_mode.py` exits 0 on it), its object is deleted, and the app pod
schedules. No object is pruned, so Argo CD's `prune` setting does not matter, and Helm changes two fields. If a
restore is still running in the recovery pod when the switch is turned off, SIGTERM ends it; that is today's
behaviour, and `restore-db.py` renames the copy into place in one step.

### 3.5 The PodDisruptionBudget

Unchanged: it selects `gsd.selectorLabels`, the app's pods only (T532-2), so the memory rule "PDB selects
Deployments only" holds. The recovery pod has no budget: a drain evicts it, the Deployment re-creates it with a new
TTL, as runbook §4 step 4 already says of an eviction.

### 3.6 `restore-db.sh`

It lists `app in (<release>,<release>-recovery)`. In recovery mode that is one pod; while the app's pod is still
terminating it is two, and the preflight refuses ("a terminating pod still counts"), which is the safe answer; on a
chart before 0.65.0 the recovery pod is still `app=<release>`. The env check (`GSD_RECOVERY_MODE`) and the
in-pod checks (no uvicorn) are unchanged.

### 3.7 The break glass (§4d)

Pause automated sync (unchanged), then `oc scale` the app's Deployment to 0 and the recovery Deployment to 1: what
`recovery.enabled: true` renders, field for field (T533-7 as rewritten). Give back by ending the pause: self-heal
puts both `replicas` back, and the scheduler orders the pods. Nothing is left to remove.

## 4. Tests

#532's body names no test IDs; these are this spec's. Each says why it fails on main.

| ID | Test | Fails on main because |
|---|---|---|
| T532-1 | `test_chart_recovery_mode.py::test_t532_1_the_switch_changes_only_the_two_deployments_replicas` (default, offsite) and `::test_t532_1_the_recovery_pod_is_the_app_pod_with_the_recovery_branches` | there is no `-recovery` Deployment |
| T532-2 | `::test_t532_2_no_selector_of_the_app_picks_the_recovery_pod_and_back` | no `-recovery` Deployment |
| T532-3 | `::test_t532_3_the_recovery_pod_waits_for_the_app_pod_and_holds_it_back_cluster_wide` | no `-recovery` Deployment, no term |
| T532-4 | `::test_t532_4_same_serviceaccount_and_security_context_and_no_uid_of_its_own` | no `-recovery` Deployment |
| T532-5 | `::test_t532_5_on_a_single_node_claim_the_offsite_copy_runs_beside_either_workloads_pod`, and `test_chart_backup_offsite.py::TestAccessModes::test_rwo_pins_the_job_to_the_dashboards_node` as rewritten | the Job's affinity has no `matchExpressions` |
| T532-6 | `::test_t532_6_the_recovery_pod_has_no_readiness_probe_and_no_selector_picks_it` (true, false) | no `-recovery` Deployment |
| T532-7 | `test_restore_db_wrapper.py::test_t532_7_the_pods_are_listed_from_both_workloads` | the script lists `app=<release>` |
| T532-8 | `test_restore_db.py::test_t532_8_the_two_messages_say_what_is_true_under_the_break_glass_too` | the two old messages |
| T532-9 | `test_runbook_backup_restore.py`: T533-5, T533-6, T533-7 and T300-10 as rewritten | the runbook still has the patch, the ConfigMap and "known limitation" |
| (existing) | T303-1, -2, -3, -14, the ConfigMap and offsite tests, T303-19's values comment, find the recovery container in the `-recovery` Deployment | — |

T303-4 (the readiness probe that cannot pass) is replaced by T532-6, and T303-15 (only the dashboard container
changes) by T532-1: the guarantees they held are now held by labels and by the two-field switch.

### 4.3 The block proof

On a throwaway worktree of `a3394ba5` (`git worktree add --detach <scratch>/apply-E11 a3394ba5…`), with
`/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/.venv/bin/python` and
`PYTHONPATH=<tree>/local-development`:

1. `python3 local-development/apply-spec-blocks.py docs/specs/SPEC_E11_recovery_workload.md <tree>` →
   `45 blocks check out across 16 files`; then `--apply`.
2. **Before** (the test blocks applied, every other block reverted with `git apply -R`), the touched test files
   `test_chart_recovery_mode.py test_restore_db_wrapper.py test_restore_db.py test_runbook_backup_restore.py
   test_recovery_mode.py test_restore_db_safety.py test_chart_backup_offsite.py`:
   `28 failed, 202 passed in 33.75s`. Every T532 test fails, each because the `-recovery` Deployment, the new selector, the new
   affinity term or the new message does not exist; T303-1, -2, -3, -14, -19 and the ConfigMap and offsite tests fail
   because they look for the recovery container in the `-recovery` Deployment; T533-5, -6, -7 because the runbook
   still has the patch.
3. **After** (all blocks), the same files plus `test_values_defaults.py test_publish_release_decision.py`:
   `246 passed in 36.04s`. On main `a3394ba5` the same nine files: `239 passed in 33.38s`.
4. `helm lint charts/group-sync-dashboard --set ingress.host=t.example.com` → `1 chart(s) linted, 0 chart(s)
   failed`; the render diffs of §2.5 (RBAC: 464 lines before and after, REMOVED 0, ADDED 0).
5. The whole suite, run once on the applied tree before the RWO offsite test was rewritten:
   `2 failed, 7565 passed, 27 skipped, 5 xfailed, 2 warnings in 600.79s` — the failures were
   `test_chart_backup_offsite.py::TestAccessModes::test_rwo_pins_the_job_to_the_dashboards_node` (its selector
   assertion, rewritten in §7; its file then `76 passed`) and the index test of Orchestrator's notes 6. The suite's
   count on main was not measured.

## 5. On the lab

The implementing pull request runs this walk (development: the lab is a development environment, so the CLI forms
below are allowed there). Read-only parts measured now are in §2.6.

1. **Before.** Record the PVC UIDs (`oc get pvc -n group-sync-dashboard -o custom-columns=NAME:.metadata.name,UID:.metadata.uid`;
   on 2026-10-02 they were data `f065b7a4-535c-4ef1-868c-58f5afee4953`, report-artifacts
   `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`, backup-offsite `7f505595-db2e-40be-a4ee-c6ed271c42b6`). Deploy the
   branch with `local-development/release-crc.sh --argocd`; both Deployments listed, the recovery one `0/0`, the
   Application Synced/Healthy.
2. **Turn it on through the values file** on a branch the Application follows (`recovery.enabled: true`), and
   record: the time the revision is applied; `oc get deploy -n group-sync-dashboard` showing `<fullname>` `0/0` and
   `<fullname>-recovery` `1/1`; the recovery pod's events showing `FailedScheduling ... didn't satisfy existing pods
   anti-affinity rules` or `didn't match pod anti-affinity rules` until the app pod is gone, then `Scheduled`;
   the Application's `status.operationState.phase` `Succeeded` with `retryCount` absent or 0, and
   `status.health.status` Healthy.
3. **Run `local-development/restore-db.sh --list`** with the defaults: it names the recovery pod
   (`<release>-recovery-…`), and `/offsite` is listed or the new note is printed.
4. **Turn it off** in the values file, and measure from the commit's apply to the app's pod Ready: one sync, no
   retry; the app pod scheduled only after the recovery pod's delete event (events and timestamps).
5. **§4d once:** pause, the two `oc scale` commands, `restore-db.sh --list`, end the pause, wait Synced, `oc
   rollout status -n $NS deploy/$REL`; record that nothing is left (`oc get deploy -o yaml` replicas equal Git).
6. **After.** The PVC UIDs again, identical.

## 6. What an operator sees, and what it costs

- `oc get deploy` lists one more Deployment, `<release>-recovery`, at `0/0`, and one more ConfigMap,
  `<release>-recovery`, in every release.
- In recovery mode: the app's Deployment `0/0`, the recovery Deployment `1/1`, its pod `2/2` (`1/1` with the proxy
  off); the Application Synced/Healthy; the route has no endpoint, as before.
- A pipeline step that waits for the rollout succeeds in recovery mode (it used to report failure).
- Turning recovery off takes one sync; the app pod starts after the recovery pod is gone (about the 30 s grace
  period at most, plus the kubelet's stop).
- `restore-db.sh` output names `app=<release> or app=<release>-recovery` when it refuses a count.
- Cost: one idle Deployment and one ConfigMap per release; one scheduler term per recovery pod. No RBAC change
  (§2.5), no image change.

## 7. Implementation blocks

The blocks were generated from the proved tree and checked with `apply-spec-blocks.py` against `a3394ba5` (§4.3).
They are applied in order; each Old text is unique in its file at the point it applies.

<!-- block: charts/group-sync-dashboard/templates/_helpers.tpl | edit -->

```
app.kubernetes.io/name: {{ include "gsd.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app: {{ include "gsd.fullname" . }}
{{- end -}}

{{- define "gsd.serviceAccountName" -}}
```

```
app.kubernetes.io/name: {{ include "gsd.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app: {{ include "gsd.fullname" . }}
{{- end -}}

{{/*
The recovery workload's pod labels and selector (#532). The `app` value differs from
gsd.selectorLabels', so the Service, the PodDisruptionBudget, the ServiceMonitor and the app's
Deployment never select the recovery pod, and its Deployment never selects an app pod.
*/}}
{{- define "gsd.recoverySelectorLabels" -}}
app.kubernetes.io/name: {{ include "gsd.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app: {{ include "gsd.fullname" . }}-recovery
app.kubernetes.io/component: recovery
{{- end -}}

{{- define "gsd.serviceAccountName" -}}
```

<!-- block: charts/group-sync-dashboard/templates/deployment.yaml | edit -->

```
{{- end }}
{{- include "gsd.reportingGuards" . }}
{{- /*
Recovery mode (#303): the same pod and the same data volume with the app stopped, for a restore.
Refused where it cannot be safe: a second recovery pod would be a second shell on the same file
(or a Pending pod), and an emptyDir has nothing to restore onto and is wiped when the pod goes.
The TTL is the bound on a forgotten recovery pod, so a value that is not a positive duration is
refused here rather than by the script after the pod has started.
*/}}
{{- $recovery := eq (include "gsd.recoveryEnabled" .) "true" }}
{{- $offsiteClaim := "" }}
{{- if $recovery }}
{{- /* Compared as text, not through `int`: `int true` is 1, and `replicaCount: true` rendered `replicas: true`
(review of the spec, Codex F3). A YAML 1 reaches here as an int or a float64, and both print "1". */}}
{{- if ne (toString .Values.replicaCount) "1" }}
```

```
{{- end }}
{{- include "gsd.reportingGuards" . }}
{{- /*
Recovery mode (#303) is its own workload (#532): this file renders two Deployments from one pod
spec, the app's and `<fullname>-recovery`, on every release. recovery.enabled sets only their
replicas (the app's to 0, the recovery one's to 1), so both report Healthy and the switch is
undone by the next rollout whatever the deployment tool prunes. Refused where it cannot be safe:
a second recovery pod would be a second shell on the same file (or a Pending pod), and an emptyDir
has nothing to restore onto and is wiped when the pod goes. The TTL is the bound on a forgotten
recovery pod, so a value that is not a positive duration is refused here rather than by the
script after the pod has started.
*/}}
{{- $recoveryOn := eq (include "gsd.recoveryEnabled" .) "true" }}
{{- /* The offsite claim, read-only, so #302's restore can list the offsite copies: the same switch
and the same claim the CronJob renders with (backup-offsite.yaml). */}}
{{- $offsiteClaim := "" }}
{{- if and (eq (include "gsd.offsiteOn" .) "true") (eq .Values.backup.offsite.destination.type "pvc") }}
{{- $offsiteClaim = .Values.backup.offsite.destination.pvc.existingClaim | default (printf "%s-backup-offsite" (include "gsd.fullname" .)) }}
{{- end }}
{{- if $recoveryOn }}
{{- /* Compared as text, not through `int`: `int true` is 1, and `replicaCount: true` rendered `replicas: true`
(review of the spec, Codex F3). A YAML 1 reaches here as an int or a float64, and both print "1". */}}
{{- if ne (toString .Values.replicaCount) "1" }}
```

<!-- block: charts/group-sync-dashboard/templates/deployment.yaml | edit -->

```
{{- end }}
{{- if eq $ttlSeconds "0" }}
{{- fail (printf "recovery.ttl %q is zero: the recovery pod would exit at once and crash-loop. Use a positive Go duration such as 2h (the default)." $ttl) }}
{{- end }}
{{- /* The offsite claim, read-only, so #302's restore can list the offsite copies: the same switch
and the same claim the CronJob renders with (backup-offsite.yaml). */}}
{{- if and (eq (include "gsd.offsiteOn" .) "true") (eq .Values.backup.offsite.destination.type "pvc") }}
{{- $offsiteClaim = .Values.backup.offsite.destination.pvc.existingClaim | default (printf "%s-backup-offsite" (include "gsd.fullname" .)) }}
{{- end }}
{{- end }}
{{- if .Values.oauthProxy.enabled }}
```

```
{{- end }}
{{- if eq $ttlSeconds "0" }}
{{- fail (printf "recovery.ttl %q is zero: the recovery pod would exit at once and crash-loop. Use a positive Go duration such as 2h (the default)." $ttl) }}
{{- end }}
{{- end }}
{{- if .Values.oauthProxy.enabled }}
```

<!-- block: charts/group-sync-dashboard/templates/deployment.yaml | edit -->

```
{{- fail (printf "oauthProxy.skipAuthRegex (%s) no longer covers /signed-out while oauthProxy.logoutUrl is empty, so the logout landing page sits BEHIND the proxy it is supposed to land outside of: the redirect from sign_out starts a fresh OAuth flow and the reader who clicked Sign out arrives back signed in. Either keep signed-out in the regex, or point oauthProxy.logoutUrl somewhere outside the proxy." .Values.oauthProxy.skipAuthRegex) }}
{{- end }}
{{- end }}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "gsd.fullname" . }}
  namespace: {{ .Release.Namespace }}
  labels: {{- include "gsd.labels" . | nindent 4 }}
spec:
  replicas: {{ .Values.replicaCount }}
  strategy:
    {{- /*
    Recreate exists for the single-replica case, where the outgoing and incoming pods would
```

```
{{- fail (printf "oauthProxy.skipAuthRegex (%s) no longer covers /signed-out while oauthProxy.logoutUrl is empty, so the logout landing page sits BEHIND the proxy it is supposed to land outside of: the redirect from sign_out starts a fresh OAuth flow and the reader who clicked Sign out arrives back signed in. Either keep signed-out in the regex, or point oauthProxy.logoutUrl somewhere outside the proxy." .Values.oauthProxy.skipAuthRegex) }}
{{- end }}
{{- end }}
{{- range $workload := list "app" "recovery" }}
{{- /* $recovery: this Deployment is the recovery workload; the pod spec below branches on it. */}}
{{- $recovery := eq $workload "recovery" }}
{{- with $ }}
{{- $selector := ternary (include "gsd.recoverySelectorLabels" .) (include "gsd.selectorLabels" .) $recovery }}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "gsd.fullname" . }}{{ if $recovery }}-recovery{{ end }}
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "gsd.labels" . | nindent 4 }}
    {{- if $recovery }}
    app.kubernetes.io/component: recovery
    {{- end }}
spec:
  {{- /* The app's Deployment at 0 is Healthy to Argo CD and to `oc rollout status` alike. */}}
  replicas: {{ if $recovery }}{{ ternary 1 0 $recoveryOn }}{{ else if $recoveryOn }}0{{ else }}{{ .Values.replicaCount }}{{ end }}
  strategy:
    {{- /*
    Recreate exists for the single-replica case, where the outgoing and incoming pods would
```

<!-- block: charts/group-sync-dashboard/templates/deployment.yaml | edit -->

```
    */}}
    type: {{ .Values.strategy | default (ternary "RollingUpdate" "Recreate" (gt (int .Values.replicaCount) 1)) }}
  selector:
    matchLabels: {{- include "gsd.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      labels:
```

```
    */}}
    type: {{ .Values.strategy | default (ternary "RollingUpdate" "Recreate" (gt (int .Values.replicaCount) 1)) }}
  selector:
    matchLabels: {{- $selector | nindent 6 }}
  template:
    metadata:
      labels:
```

<!-- block: charts/group-sync-dashboard/templates/deployment.yaml | edit -->

```
               by name rather than reorder the includes, which would discard the operator's label
               silently (review of chart 0.14.0, second pass). */}}
        {{- range $k, $_ := .Values.podLabels }}
        {{- if hasKey (include "gsd.selectorLabels" $ | fromYaml) $k }}
        {{- fail (printf "podLabels must not set %q: it is one of the selector labels the Service, the PodDisruptionBudget and the Deployment select the pod by" $k) }}
        {{- end }}
        {{- end }}
        {{- include "gsd.selectorLabels" . | nindent 8 }}
        {{- with .Values.podLabels }}{{- toYaml . | nindent 8 }}{{- end }}
      annotations:
        # Restart the pod when the config changes. Without this a `helm upgrade` that only
```

```
               by name rather than reorder the includes, which would discard the operator's label
               silently (review of chart 0.14.0, second pass). */}}
        {{- range $k, $_ := .Values.podLabels }}
        {{- if hasKey ($selector | fromYaml) $k }}
        {{- fail (printf "podLabels must not set %q: it is one of the selector labels the Service, the PodDisruptionBudget and the Deployment select the pod by" $k) }}
        {{- end }}
        {{- end }}
        {{- $selector | nindent 8 }}
        {{- with .Values.podLabels }}{{- toYaml . | nindent 8 }}{{- end }}
      annotations:
        # Restart the pod when the config changes. Without this a `helm upgrade` that only
```

<!-- block: charts/group-sync-dashboard/templates/deployment.yaml | edit -->

```
      {{- with .Values.tolerations }}
      tolerations: {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with .Values.affinity }}
      affinity: {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with .Values.priorityClassName }}
```

```
      {{- with .Values.tolerations }}
      tolerations: {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- $affinity := deepCopy (.Values.affinity | default dict) }}
      {{- if $recovery }}
      {{- /* THE ORDERING ON THE DATA CLAIM (#532). The scheduler places no recovery pod while a pod
      with the app's selector labels exists, terminating ones included, and no app pod while a
      recovery pod exists (it applies an existing pod's required anti-affinity to the incoming
      pod), so the two never hold gsd.db at once. kubernetes.io/os has one value on every node that
      can run this image, which makes the domain the whole cluster rather than one node. */}}
      {{- $anti := $affinity.podAntiAffinity | default dict }}
      {{- $term := dict "labelSelector" (dict "matchLabels" (include "gsd.selectorLabels" . | fromYaml)) "topologyKey" "kubernetes.io/os" }}
      {{- $_ := set $anti "requiredDuringSchedulingIgnoredDuringExecution" (append ($anti.requiredDuringSchedulingIgnoredDuringExecution | default list) $term) }}
      {{- $_ := set $affinity "podAntiAffinity" $anti }}
      {{- end }}
      {{- with $affinity }}
      affinity: {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with .Values.priorityClassName }}
```

<!-- block: charts/group-sync-dashboard/templates/deployment.yaml | edit -->

```
            timeoutSeconds: {{ .Values.probes.liveness.timeoutSeconds }}
            failureThreshold: {{ .Values.probes.liveness.failureThreshold }}
          {{- end }}
          {{- if $recovery }}
          # RECOVERY MODE: a readiness probe that cannot pass, whatever probes.readiness says, so the
          # pod never joins the Service. A container with no readiness probe counts as ready, and
          # the Service would send readers to a proxy whose upstream has no listener. Nothing listens
          # on 8080 while the app is stopped; a TCP probe needs no exec and touches no proxy.
          readinessProbe:
            tcpSocket:
              port: http
            periodSeconds: 30
            timeoutSeconds: 5
            failureThreshold: 1
          {{- else if .Values.probes.readiness.enabled }}
          readinessProbe:
            httpGet:
              path: {{ .Values.probes.readiness.path }}
```

```
            timeoutSeconds: {{ .Values.probes.liveness.timeoutSeconds }}
            failureThreshold: {{ .Values.probes.liveness.failureThreshold }}
          {{- end }}
          {{- /* No readiness probe in the recovery workload (#532): no Service selects its pod, so it
          counts as ready once it runs and its Deployment reports available. */}}
          {{- if and .Values.probes.readiness.enabled (not $recovery) }}
          readinessProbe:
            httpGet:
              path: {{ .Values.probes.readiness.path }}
```

<!-- block: charts/group-sync-dashboard/templates/deployment.yaml | edit -->

```
            secretName: {{ include "gsd.fullname" . }}-oauth-session
            defaultMode: 420
        {{- end }}
```

```
            secretName: {{ include "gsd.fullname" . }}-oauth-session
            defaultMode: 420
        {{- end }}
{{- end }}
{{- end }}
```

<!-- block: charts/group-sync-dashboard/templates/recovery.yaml | edit -->

```
{{- if eq (include "gsd.recoveryEnabled" .) "true" }}
# Recovery mode's script (#303), verbatim from scripts/recovery_mode.py; a test holds the two
# identical. Rendered only while recovery.enabled is true, so the default render has no extra object.
apiVersion: v1
kind: ConfigMap
metadata:
```

```
# Recovery mode's script (#303), verbatim from scripts/recovery_mode.py; a test holds the two
# identical. Rendered on every release, like the recovery Deployment that mounts it (#532), so
# turning recovery mode on or off changes only the two Deployments' replicas.
apiVersion: v1
kind: ConfigMap
metadata:
```

<!-- block: charts/group-sync-dashboard/templates/recovery.yaml | edit -->

```
data:
  recovery_mode.py: |
{{ .Files.Get "scripts/recovery_mode.py" | indent 4 }}
{{- end }}
```

```
data:
  recovery_mode.py: |
{{ .Files.Get "scripts/recovery_mode.py" | indent 4 }}
```

<!-- block: charts/group-sync-dashboard/templates/backup-offsite.yaml | edit -->

```
          {{- end }}
          {{- if ne $mode "ReadWriteMany" }}
          # ReadWriteOnce binds the data claim to one NODE. Pods on that node may share it, so
          # the copy runs beside the dashboard; on any other node it could never mount.
          affinity:
            podAffinity:
              requiredDuringSchedulingIgnoredDuringExecution:
                - topologyKey: kubernetes.io/hostname
                  labelSelector:
                    matchLabels: {{- include "gsd.selectorLabels" . | nindent 22 }}
          {{- end }}
          {{- if eq $type "s3" }}
          initContainers:
```

```
          {{- end }}
          {{- if ne $mode "ReadWriteMany" }}
          # ReadWriteOnce binds the data claim to one NODE. Pods on that node may share it, so
          # the copy runs beside the pod that holds it: the app's, or in recovery mode the
          # recovery workload's (#532); on any other node it could never mount.
          affinity:
            podAffinity:
              requiredDuringSchedulingIgnoredDuringExecution:
                - topologyKey: kubernetes.io/hostname
                  labelSelector:
                    matchLabels:
                      app.kubernetes.io/name: {{ include "gsd.name" . }}
                      app.kubernetes.io/instance: {{ .Release.Name }}
                    matchExpressions:
                      - key: app
                        operator: In
                        values:
                          - {{ include "gsd.fullname" . }}
                          - {{ include "gsd.fullname" . }}-recovery
          {{- end }}
          {{- if eq $type "s3" }}
          initContainers:
```

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->

```
    failureThreshold: 3

# ---------------------------------------------------------------------------
# Recovery mode (#303) — the pod with the data volume mounted and the app stopped
# ---------------------------------------------------------------------------
# For a restore or a rollback (docs/RUNBOOK_backup_restore.md section 4). recovery.enabled=true
# runs the chart's recovery script (scripts/recovery_mode.py, shipped in a ConfigMap) in the
# dashboard container instead of uvicorn, on the same pod spec and the same /data volume: no process opens
# gsd.db, so you can replace it from `oc exec`, and a dropped session does not end the pod. The
# script ships with the chart, not the image, so it runs under the older image a rollback targets.
# At one replica the strategy is Recreate, so the writer stops before the recovery pod starts.
#
# SET IT IN THIS RELEASE'S VALUES FILE and roll it out through the release's deployment pipeline,
# like any other value; for a rollback, set the older image.tag in the same change. Never with
```

```
    failureThreshold: 3

# ---------------------------------------------------------------------------
# Recovery mode (#303) — the app stopped and a recovery pod holding the data volume
# ---------------------------------------------------------------------------
# For a restore or a rollback (docs/RUNBOOK_backup_restore.md section 4). The chart renders a second
# Deployment, <fullname>-recovery, on every release (#532): the app's pod spec and the same /data
# volume, with the chart's recovery script (scripts/recovery_mode.py, shipped in a ConfigMap) in the
# dashboard container instead of uvicorn, at 0 replicas. recovery.enabled=true scales the app's
# Deployment to 0 and the recovery Deployment to 1, and false the other way round: nothing else
# changes, so both Deployments report available and the next rollout turns it off whatever the
# deployment tool prunes. No process opens gsd.db in the recovery pod, so you can replace it from
# `oc exec`, and a dropped session does not end the pod. The script ships with the chart, not the
# image, so it runs under the older image a rollback targets. The scheduler starts the recovery pod
# only once the app's pod is gone, and the app's only once the recovery pod is gone (a required pod
# anti-affinity on the recovery pod), so the two never hold the database at once.
#
# SET IT IN THIS RELEASE'S VALUES FILE and roll it out through the release's deployment pipeline,
# like any other value; for a rollback, set the older image.tag in the same change. Never with
```

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->

```
# edit, and an environment variable alone would leave the liveness probe to kill the pod in the
# middle of a restore.
#
# While it is on the pod has no liveness probe, and a readiness probe that cannot pass keeps it
# out of the Service: READY reads 1/2 (the oauth-proxy sidecar is ready, the dashboard is not; 0/1
# with the proxy off), the route has no ready endpoint, and the Deployment never reports available,
# so a pipeline step that waits for the rollout reports it failed. A pipeline that rolls a failed
# rollout back on its own (Helm's --rollback-on-failure flag, --atomic in Helm 3, or an equivalent
# remediation) must not carry this change: the rollback turns recovery mode off by itself and starts
# the app on a file that may be half restored. When backup.offsite uses the pvc destination, its
# claim is mounted read-only at /offsite, so the offsite copies can be listed and read.
#
# NOTHING IS RECORDED WHILE IT IS ON, and no rule says recovery mode. GroupSyncDashboardNotPolling
# does not fire: its gauge comes from the stopped process, and a missing series returns nothing.
```

```
# edit, and an environment variable alone would leave the liveness probe to kill the pod in the
# middle of a restore.
#
# The recovery pod has no liveness probe and no readiness probe, and no Service selects it: READY
# reads 2/2 (1/1 with the proxy off), the route has no endpoint, and both Deployments report
# available. A pipeline that rolls a failed rollout back on its own (Helm's --rollback-on-failure
# flag, --atomic in Helm 3, or an equivalent remediation) must still not carry this change: a
# rollout that fails for another reason is rolled back, which turns recovery mode off by itself and
# starts the app on a file that may be half restored. When backup.offsite uses the pvc destination,
# its claim is mounted read-only at /offsite, so the offsite copies can be listed and read.
#
# NOTHING IS RECORDED WHILE IT IS ON, and no rule says recovery mode. GroupSyncDashboardNotPolling
# does not fire: its gauge comes from the stopped process, and a missing series returns nothing.
```

<!-- block: charts/group-sync-dashboard/README.md | edit -->

```

| Key | Default | Notes |
|---|---|---|
| `recovery.enabled` | `false` | **stops the dashboard.** The dashboard container runs the chart's recovery script instead of uvicorn, on the same pod spec and the same `/data` volume, so no process holds `gsd.db` while you restore it. No liveness probe; a readiness probe that cannot pass keeps the pod out of the Service. Refused with `replicaCount` other than 1 and with `persistence.enabled=false` |
| `recovery.ttl` | `2h` | a Go duration (`2h`, `90m`, `1h30m`), counted from the pod's first start and kept in its `/tmp` across container restarts; a new pod (a new value, a deleted or evicted pod) starts a new TTL. At the TTL every process in the container stops, an `oc exec` restore still running included, the pod goes to `CrashLoopBackOff` and its log says how to extend or leave recovery mode. Refused when it is not a duration or is zero |

Set both in the release's values file and roll them out through the release's deployment pipeline, like any
other value; for a rollback, set the older `image.tag` in the same change. Never with `oc set env`: a GitOps
tool such as Argo CD (selfHeal) reverts a hand edit of the Deployment, and the variable alone would leave the
liveness probe to kill the pod in the middle of a restore. The script
(`charts/group-sync-dashboard/scripts/recovery_mode.py`) ships in a ConfigMap rendered only while recovery
is on, not in the image, so it runs under the older image a rollback targets; it imports only the standard
library and opens nothing under `/data`. With `backup.offsite` on its `pvc` destination, the offsite claim
is mounted read-only at `/offsite`. The pod reads `1/2` ready with the oauth-proxy sidecar (the sidecar is
ready, the dashboard is not) and `0/1` with the proxy off; the Deployment never reports available, so a
pipeline step that waits for the rollout reports it failed. A pipeline that rolls a failed rollout back on its
own (Helm's `--rollback-on-failure` flag, `--atomic` in Helm 3, or an equivalent remediation) must not carry
this change: the rollback turns recovery mode off by itself and starts the app on a file that may be half
restored.

**Nothing is recorded while it is on.** No rule says recovery mode: `GroupSyncDashboardNotPolling` does not
fire, because its gauge comes from the stopped process and a missing series returns nothing. With
```

```

| Key | Default | Notes |
|---|---|---|
| `recovery.enabled` | `false` | **stops the dashboard.** Scales the app's Deployment to 0 and `<fullname>-recovery` to 1 (#532): the app's pod spec and the same `/data` volume, with the chart's recovery script instead of uvicorn, so no process holds `gsd.db` while you restore it. The scheduler starts each workload's pod only once the other's is gone. No liveness or readiness probe; no Service selects the recovery pod. Refused with `replicaCount` other than 1 and with `persistence.enabled=false` |
| `recovery.ttl` | `2h` | a Go duration (`2h`, `90m`, `1h30m`), counted from the pod's first start and kept in its `/tmp` across container restarts; a new pod (a new value, a deleted or evicted pod) starts a new TTL. At the TTL every process in the container stops, an `oc exec` restore still running included, the pod goes to `CrashLoopBackOff` and its log says how to extend or leave recovery mode. Refused when it is not a duration or is zero |

Set both in the release's values file and roll them out through the release's deployment pipeline, like any
other value; for a rollback, set the older `image.tag` in the same change. Never with `oc set env`: a GitOps
tool such as Argo CD (selfHeal) reverts a hand edit of the Deployment, and the variable alone would leave the
liveness probe to kill the pod in the middle of a restore. The script
(`charts/group-sync-dashboard/scripts/recovery_mode.py`) ships in a ConfigMap, not in the image, so it runs
under the older image a rollback targets; it imports only the standard library and opens nothing under
`/data`. The recovery Deployment and its ConfigMap are rendered on every release at 0 replicas, so the switch
changes only the two Deployments' `replicas` and the next rollout undoes it whatever the deployment tool
prunes. With `backup.offsite` on its `pvc` destination, the offsite claim is mounted read-only at `/offsite`.
The recovery pod reads `2/2` ready with the oauth-proxy sidecar and `1/1` with the proxy off, and both
Deployments report available. A pipeline that rolls a failed rollout back on its own (Helm's
`--rollback-on-failure` flag, `--atomic` in Helm 3, or an equivalent remediation) must still not carry this
change: a rollout that fails for another reason is rolled back, which turns recovery mode off by itself and
starts the app on a file that may be half restored.

**Nothing is recorded while it is on.** No rule says recovery mode: `GroupSyncDashboardNotPolling` does not
fire, because its gauge comes from the stopped process and a missing series returns nothing. With
```

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->

```
# CHART 0.62.0 (2026-10-02), MINOR: appVersion moves to application 3.1.0 (below); Delete report
# runs and database copies from the page, previewed and confirmed, for the cluster-admin tier
# (#542).
version: 0.62.0
# 0.8.0 (2026-09-03). A Users tab — every user with a synced membership, filtered as you type on
# id or display name — and a Find member box on the group page. /users rows gain `full_name`,
# nullable, the same field the members list already carried. Additive on the wire and in the UI,
```

```
# CHART 0.62.0 (2026-10-02), MINOR: appVersion moves to application 3.1.0 (below); Delete report
# runs and database copies from the page, previewed and confirmed, for the cluster-admin tier
# (#542).
# CHART 0.65.0, MINOR: recovery mode is its own workload (#532). A second Deployment,
# <fullname>-recovery, is rendered on every release at 0 replicas; recovery.enabled scales the
# app's to 0 and it to 1, so both report available and turning it off takes one rollout. A required
# pod anti-affinity orders the two pods on the data claim. No RBAC change.
version: 0.65.0
# 0.8.0 (2026-09-03). A Users tab — every user with a synced membership, filtered as you type on
# id or display name — and a Find member box on the group page. /users rows gain `full_name`,
# nullable, the same field the members list already carried. Additive on the wire and in the UI,
```

<!-- block: local-development/restore-db.sh | edit -->

```
#   local-development/restore-db.sh --list
#   local-development/restore-db.sh --from-version <ID> [--yes]
#   options: --namespace <ns> (default group-sync-dashboard)
#            --release <name> (default group-sync-dashboard: the pods are found by app=<name>, as in the runbook)
#
# Runs on your laptop with oc, as you: nothing is added to any ServiceAccount; you need get on pods and
# create on pods/exec in the namespace. It refuses unless the release's one pod is in recovery mode (#303:
```

```
#   local-development/restore-db.sh --list
#   local-development/restore-db.sh --from-version <ID> [--yes]
#   options: --namespace <ns> (default group-sync-dashboard)
#            --release <name> (default group-sync-dashboard: the pods are found by app=<name>-recovery, or
#                              app=<name> on a chart before 0.65.0, as in the runbook)
#
# Runs on your laptop with oc, as you: nothing is added to any ServiceAccount; you need get on pods and
# create on pods/exec in the namespace. It refuses unless the release's one pod is in recovery mode (#303:
```

<!-- block: local-development/restore-db.sh | edit -->

```

# The release's one pod, in recovery mode, with enough of its TTL left: read from the pod spec, no exec.
# Prints "<pod>\t<image>\t<time left>", or refuses (exit 2) with the reason and what to set.
preflight() {
  local pods
  pods=$(oc get pods -n "${NS}" -l "app=${REL}" -o json) || return
  printf '%s' "${pods}" | python3 "${HELPER}" preflight --release "${REL}" --namespace "${NS}"
}

```

```

# The release's one pod, in recovery mode, with enough of its TTL left: read from the pod spec, no exec.
# Prints "<pod>\t<image>\t<time left>", or refuses (exit 2) with the reason and what to set.
# Both workloads' pods are listed (#532): an app pod still terminating beside the recovery pod makes two,
# and two are refused.
preflight() {
  local pods
  pods=$(oc get pods -n "${NS}" -l "app in (${REL},${REL}-recovery)" -o json) || return
  printf '%s' "${pods}" | python3 "${HELPER}" preflight --release "${REL}" --namespace "${NS}"
}

```

<!-- block: local-development/restore-db.py | edit -->

```
    pods = doc.get("items") or []
    names = [p["metadata"]["name"] for p in pods]
    if len(pods) != 1:
        raise Refused(EXIT_POD, f"{len(pods)} pods match app={release} in {namespace} ({', '.join(names) or 'none'}); "
                                "a restore needs exactly one, the release's recovery pod. Wait until one is left "
                                "(a terminating pod still counts), then run this again")
    pod, name = pods[0], names[0]
```

```
    pods = doc.get("items") or []
    names = [p["metadata"]["name"] for p in pods]
    if len(pods) != 1:
        raise Refused(EXIT_POD, f"{len(pods)} pods match app={release} or app={release}-recovery in {namespace} "
                                f"({', '.join(names) or 'none'}); "
                                "a restore needs exactly one, the release's recovery pod. Wait until one is left "
                                "(a terminating pod still counts), then run this again")
    pod, name = pods[0], names[0]
```

<!-- block: local-development/restore-db.py | edit -->

```
    if lay.backup is None:
        say("# backup: config.backup is off (no backupDir), so there are no scheduled backups to list")
    if not lay.offsite.is_dir():
        say(f"# offsite: {lay.offsite} is not mounted (recovery mode mounts the offsite claim only when backup.offsite "
            "uses its pvc destination)")
    for line in notes + aside_notes(lay, known):
        say(line)
    return 0
```

```
    if lay.backup is None:
        say("# backup: config.backup is off (no backupDir), so there are no scheduled backups to list")
    if not lay.offsite.is_dir():
        say(f"# offsite: {lay.offsite} is not mounted in this pod. The chart's recovery pod mounts the offsite claim, "
            "read-only, when backup.offsite uses its pvc destination; restore a copy that is only on that claim with "
            "docs/RUNBOOK_backup_restore.md section 4b")
    for line in notes + aside_notes(lay, known):
        say(line)
    return 0
```

<!-- block: local-development/restore-db.py | edit -->

```
        "-wal into it)")
    say(f"written      {lay.db} <- {row.path} · sha256 {digest} · chgrp {group} · chmod g=u")
    say(f"user_version {'absent' if before is None else before} -> {after}")
    say("restored. Set recovery.enabled: false in this release's values file and roll it out through the release's "
        "deployment pipeline: the app starts on the restored file.")
    if kept:
        say(f"way back     {kept}/ is the database as it was; docs/RUNBOOK_backup_restore.md section 4, \"Undo a "
            "restore\", puts it back (fold it first: its rows may be only in its -wal)")
```

```
        "-wal into it)")
    say(f"written      {lay.db} <- {row.path} · sha256 {digest} · chgrp {group} · chmod g=u")
    say(f"user_version {'absent' if before is None else before} -> {after}")
    say("restored. Turn recovery mode off the way it was turned on: set recovery.enabled: false in this release's "
        "values file and roll it out through the release's deployment pipeline, or, under the break glass "
        "(docs/RUNBOOK_backup_restore.md section 4d), give the release back to Git (its step 5). The app starts on "
        "the restored file once the recovery pod is gone.")
    if kept:
        say(f"way back     {kept}/ is the database as it was; docs/RUNBOOK_backup_restore.md section 4, \"Undo a "
            "restore\", puts it back (fold it first: its rows may be only in its -wal)")
```

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

```
>   Application reading Synced). A hand recovery edit is both: self-heal would restore the app's command and liveness
>   probe and start the app, perhaps on a half-restored database, while the pod still carries the recovery variables.
>   Pause automated sync first and confirm the pause held (§4d steps 1 and 2).
> * **The endless retry.** Recovery mode never reports healthy, so a sync that turns it on through the values file
>   fails at the Deployment's progress deadline and is retried under the Application's `syncPolicy.retry`, and every
>   later change, `recovery.enabled: false` included, waits until the last retry has failed: 12 min 49 s on the lab
>   with `limit: 3` and a 30 s backoff doubling up to 5 min (#532). A `limit` less than 0 retries without end, and an
>   automated sync with no `retry` block retries 5 times. Meanwhile the Application reads OutOfSync with its
>   operation Running (`Retrying attempt #N`), the new revision is not applied, and the recovery pod stays `1/2`.
>   The way out is §4d step 7: pause, then end the running operation.

**The script, in recovery mode (#302).** With the release's pod in recovery mode (#303: `recovery.enabled: true`
in the release's values file), run `local-development/restore-db.sh --list` from your laptop, then
```

```
>   Application reading Synced). A hand recovery edit is both: self-heal would restore the app's command and liveness
>   probe and start the app, perhaps on a half-restored database, while the pod still carries the recovery variables.
>   Pause automated sync first and confirm the pause held (§4d steps 1 and 2).
> * **The endless retry, on a chart before 0.65.0.** There, recovery mode never reports healthy, so a sync that turns
>   it on through the values file fails at the Deployment's progress deadline and is retried under the Application's
>   `syncPolicy.retry`, and every later change, `recovery.enabled: false` included, waits until the last retry has
>   failed: 12 min 49 s on the lab with `limit: 3` and a 30 s backoff doubling up to 5 min (#532). A `limit` less
>   than 0 retries without end, and an automated sync with no `retry` block retries 5 times. Meanwhile the
>   Application reads OutOfSync with its operation Running (`Retrying attempt #N`), the new revision is not applied,
>   and the recovery pod stays `1/2`. The way out is §4d step 7: pause, then end the running operation. From chart
>   0.65.0 recovery mode is its own Deployment and both Deployments report Healthy, so there is nothing to retry.

**The script, in recovery mode (#302).** With the release's pod in recovery mode (#303: `recovery.enabled: true`
in the release's values file), run `local-development/restore-db.sh --list` from your laptop, then
```

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

```
   `recovery.enabled: true` and `recovery.ttl` (for example `2h`, longer than the restore needs), and roll it
   out. For a rollback, set the older `image.tag` in the same change, so the restore runs under the image
   that will open the file.
2. **Wait for the recovery pod.** `oc get pods -n $NS -l app=$REL` shows `1/2` ready (`0/1` with the proxy
   off) and `Running`: the dashboard container is not ready, so the Service sends it nothing.
   `oc logs -n $NS deploy/$REL -c dashboard` starts with `RECOVERY MODE`, `the app is NOT running and no data
   is collected` and the TTL's end. With `backup.offsite` on its `pvc` destination, the offsite claim is at
   `/offsite`, read-only. The Deployment never reports available, so a pipeline step that waits for the
   rollout reports it failed; that is expected. A pipeline that rolls a failed rollout back on its own (Helm's
   `--rollback-on-failure` flag, `--atomic` in Helm 3, or an equivalent remediation) must not carry this
   change: the rollback turns recovery mode off by itself and starts the app on a file that may be half
   restored.
3. **Restore** with `local-development/restore-db.sh --list`, then `--from-version <ID>` (**The script, in recovery
   mode**, above), each with `--namespace $NS --release $REL` unless both are the script's defaults
   (`group-sync-dashboard`); it refuses with less than ten minutes of `recovery.ttl` left. By hand, the fallback, use
   §4a or §4b, running their commands with `oc exec -n $NS deploy/$REL -c dashboard -- sh -c '…'` instead of `oc debug`
   or a helper pod. **Check the time left first** (the last `left` line of `oc logs`):
   at the TTL the script exits and every process in the container stops with it, a restore still running
   included, which leaves `gsd.db` half written. If the restore may not finish in time, extend first.
```

```
   `recovery.enabled: true` and `recovery.ttl` (for example `2h`, longer than the restore needs), and roll it
   out. For a rollback, set the older `image.tag` in the same change, so the restore runs under the image
   that will open the file.
2. **Wait for the recovery pod.** The app's Deployment goes to 0 and `$REL-recovery` to 1 (chart 0.65.0 and
   later, #532); the scheduler holds the recovery pod `Pending` until the app's pod is gone.
   `oc get pods -n $NS -l app=$REL-recovery` then shows `2/2` ready (`1/1` with the proxy off) and `Running`; no
   Service selects it. `oc logs -n $NS deploy/$REL-recovery -c dashboard` starts with `RECOVERY MODE`, `the app is
   NOT running and no data is collected` and the TTL's end. With `backup.offsite` on its `pvc` destination, the
   offsite claim is at `/offsite`, read-only. Both Deployments report available, so a pipeline step that waits for
   the rollout succeeds. A pipeline that rolls a failed rollout back on its own (Helm's `--rollback-on-failure`
   flag, `--atomic` in Helm 3, or an equivalent remediation) must still not carry this change: a rollout that
   fails for another reason is rolled back, which turns recovery mode off by itself and starts the app on a file
   that may be half restored.
3. **Restore** with `local-development/restore-db.sh --list`, then `--from-version <ID>` (**The script, in recovery
   mode**, above), each with `--namespace $NS --release $REL` unless both are the script's defaults
   (`group-sync-dashboard`); it refuses with less than ten minutes of `recovery.ttl` left. By hand, the fallback, use
   §4a or §4b, running their commands with `oc exec -n $NS deploy/$REL-recovery -c dashboard -- sh -c '…'` instead of `oc debug`
   or a helper pod. **Check the time left first** (the last `left` line of `oc logs`):
   at the TTL the script exits and every process in the container stops with it, a restore still running
   included, which leaves `gsd.db` half written. If the restore may not finish in time, extend first.
```

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

```
   monotonic clock, so setting the wall clock back does not lengthen it; if the node restarts under the pod,
   the TTL counts as reached.
5. **Turn it off**, and verify with §4c: set `recovery.enabled: false` in the values file (keep a rollback's
   older `image.tag`) and roll it out. When the change is applied the recovery pod stops and the app starts on the
   restored file. Where the release's GitOps controller retries a failed sync (a `syncPolicy.retry` policy), the
   change waits until the retries of the sync that turned recovery on have run out, 12 min 49 s on the lab, and the
   recovery pod keeps running until then (#532, a known limitation of this release, and the risks box above).

Nothing is recorded while recovery mode is on, and no rule says so: `GroupSyncDashboardNotPolling` reads a
gauge the stopped process no longer emits, so it returns nothing. With reporting on,
```

```
   monotonic clock, so setting the wall clock back does not lengthen it; if the node restarts under the pod,
   the TTL counts as reached.
5. **Turn it off**, and verify with §4c: set `recovery.enabled: false` in the values file (keep a rollback's
   older `image.tag`) and roll it out. The rollout scales the recovery Deployment to 0 and the app's back to 1; the
   scheduler holds the app's pod until the recovery pod is gone, and the app starts on the restored file within
   the one rollout (#532). On a chart before 0.65.0, where the release's GitOps controller retries a failed sync (a
   `syncPolicy.retry` policy), the change waits until the retries of the sync that turned recovery on have run
   out, 12 min 49 s on the lab, and the recovery pod keeps running until then (the risks box above).

Nothing is recorded while recovery mode is on, and no rule says so: `GroupSyncDashboardNotPolling` reads a
gauge the stopped process no longer emits, so it returns nothing. With reporting on,
```

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

```

For an incident on a release Argo CD syncs (#533; the operator's decision of 2026-10-02). It replaces steps 1, 2 and
5 of the values-file path; the restore is the same script. Every step was walked on the CRC lab (Argo CD v3.4.7, chart
0.61.2), the restore and step 7 included (SPEC_E10's §5 walk, 2026-10-02); the ApplicationSet case follows Argo CD's
documentation. You need the right to patch the release's Application in Argo CD's namespace, `helm`, and a release at one replica (recovery
mode and `restore-db.sh` need exactly one pod).

1. **Find the Application, and whether an ApplicationSet owns it.** The Deployment's tracking annotation reads
```

```

For an incident on a release Argo CD syncs (#533; the operator's decision of 2026-10-02). It replaces steps 1, 2 and
5 of the values-file path; the restore is the same script. Every step was walked on the CRC lab (Argo CD v3.4.7, chart
0.61.2), the restore and step 7 included (SPEC_E10's §5 walk, 2026-10-02); steps 3, 5 and 6 as chart 0.65.0 changes
them (#532) are walked by SPEC_E11's §5; the ApplicationSet case follows Argo CD's
documentation. You need the right to patch the release's Application in Argo CD's namespace, to scale the release's Deployments, and a release at one replica (recovery
mode and `restore-db.sh` need exactly one pod).

1. **Find the Application, and whether an ApplicationSet owns it.** The Deployment's tracking annotation reads
```

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

```
   It must print `false` and a phase that is not `Running`, and the same a minute later. With `enabled: false` Argo CD
   runs neither automated sync nor self-heal for this Application ("controller will skip automated sync even if
   `prune`, `self-heal` and `allowEmpty` are set"), and `prune` and `selfHeal` stay as they were for step 5. A sync
   already running is not stopped by the pause: it goes on waiting for the Deployment to be healthy, which the hand
   edit of step 3 never is, fails at the progress deadline and is retried, and each retry applies what Git renders
   over the hand edit, so the app would start on a file a restore may still be writing. With `Running`, terminate the
   operation first (step 7's command) and confirm again.
3. **Put the pod into recovery mode by hand.** Setting `GSD_RECOVERY_MODE` alone is not enough: the app keeps running
   with the variable set, and `restore-db.sh --list` refuses with `uvicorn is running here (pid 1)` (measured). The
   edit is what `recovery.enabled: true` renders for the dashboard container
   (`charts/group-sync-dashboard/templates/deployment.yaml#RECOVERY MODE (#303)`): the chart's recovery script, from
   the chart version the release runs, in the ConfigMap the chart would create, as the container's command, with the
   two variables and without the liveness probe (nothing serves `/healthz`, and a kill would end a restore). The
   readiness probe stays and fails, so the Service sends the pod nothing. `TTL` is how long the pod waits for you (§4
   step 1), counted from its start:

   ````sh
   oc get deploy -n $NS $REL -o jsonpath='{.metadata.labels.helm\.sh/chart}{"\n"}'
   helm pull group-sync-dashboard --repo https://ephico2real2.github.io/group-sync-dashboard --version <the version after group-sync-dashboard-> --untar --untardir ./break-glass
   oc create configmap -n $NS $REL-recovery --from-file=recovery_mode.py=./break-glass/group-sync-dashboard/scripts/recovery_mode.py
   TTL=2h
   oc patch -n $NS deploy/$REL --type strategic -p '{"spec":{"template":{"spec":{"containers":[{"name":"dashboard","command":["python3.14","/scripts/recovery_mode.py","--release","'$REL'"],"livenessProbe":null,"env":[{"name":"GSD_RECOVERY_MODE","value":"true"},{"name":"GSD_RECOVERY_MODE_TTL","value":"'$TTL'"}],"volumeMounts":[{"name":"recovery-script","mountPath":"/scripts","readOnly":true}]}],"volumes":[{"name":"recovery-script","configMap":{"name":"'$REL'-recovery","defaultMode":292}}]}}}}'
   ````

   The app stops before the recovery pod starts (the chart's `Recreate` strategy at one replica). Wait until
   `oc get pods -n $NS -l app=$REL` shows one pod `1/2` `Running` whose log starts with `RECOVERY MODE` (§4 step 2);
   on the lab it took 4 s. The offsite claim is not mounted by this edit: restore a copy that is only on `/offsite`
   with §4b. For more time, run the patch again with a longer `TTL`; the new pod counts it from its start.
4. **Restore** with the script, as **The script, in recovery mode** says. It accepted this pod on the lab (`recovery
   mode, at least 1h59m56s of its TTL left`), listed its copies, and restored the newest (a loss window of 5m44s, no
   rows discarded):
```

```
   It must print `false` and a phase that is not `Running`, and the same a minute later. With `enabled: false` Argo CD
   runs neither automated sync nor self-heal for this Application ("controller will skip automated sync even if
   `prune`, `self-heal` and `allowEmpty` are set"), and `prune` and `selfHeal` stay as they were for step 5. A sync
   already running is not stopped by the pause: if it fails it is retried, and each retry applies what Git renders
   over the hand edit, so the app would start on a file a restore may still be writing. With `Running`, terminate the
   operation first (step 7's command) and confirm again.
3. **Put the release into recovery mode by hand.** The chart renders the recovery Deployment, `$REL-recovery`, on
   every release at 0 replicas (chart 0.65.0 and later, #532), so the hand edit is the two `replicas` that
   `recovery.enabled: true` renders, and nothing else: the pod is the chart's own recovery pod, with the release's
   `recovery.ttl` and, on the `pvc` destination, the offsite claim at `/offsite`. The scheduler starts the recovery
   pod only once the app's pod is gone (its required pod anti-affinity), whichever command runs first:

   ````sh
   oc scale -n $NS deploy/$REL --replicas=0
   oc scale -n $NS deploy/$REL-recovery --replicas=1
   ````

   Wait until `oc get pods -n $NS -l app=$REL-recovery` shows one pod `2/2` `Running` whose log starts with
   `RECOVERY MODE` (§4 step 2). For more time, `oc rollout restart -n $NS deploy/$REL-recovery`: the new pod counts
   the TTL from its start, and the restart ends any `oc exec` in the old one.

4. **Restore** with the script, as **The script, in recovery mode** says. It accepted this pod on the lab (`recovery
   mode, at least 1h59m56s of its TTL left`), listed its copies, and restored the newest (a loss window of 5m44s, no
   rows discarded):
```

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

```
   oc rollout status -n $NS deploy/$REL
   ````

   With `selfHeal: true` Argo CD puts back the command and the liveness probe and the app starts on the restored file
   (on the lab the command was back 2.6 s after the patch, the rollout done 19.8 s after, the Application
   Synced/Healthy). The wait comes first because `oc rollout status` run before Argo CD's apply reports the recovery
   rollout, which never completed: after ten minutes in recovery mode (the Deployment's progress deadline) it fails
   at once with `exceeded its progress deadline` (measured). With `selfHeal` off and Git unchanged, automated sync
   does not sync a revision it has already synced ("a second sync will not be attempted, unless `selfHeal` flag is
   set to true"): sync the Application once from Argo CD, and the wait ends when it has (not measured). The
   operator's alternative for a rollback is Argo CD's history and rollback, while still paused (Argo CD refuses it
   while automated sync is on); commit the same values to Git before you end the pause, or automated sync takes the
   release back to what Git says.
6. **Remove what the hand edit added.** Argo CD applies only what it renders, so it leaves the two variables, the
   `/scripts` mount and its volume in place and still reads Synced (measured). Remove them, and the ConfigMap, once
   the app runs. The pod restarts once more (19 s on the lab); afterwards the pod template equals the one before the
   incident (on the lab, 0 of 163 fields differed):

   ````sh
   oc patch -n $NS deploy/$REL --type strategic -p '{"spec":{"template":{"spec":{"containers":[{"name":"dashboard","env":[{"name":"GSD_RECOVERY_MODE","$patch":"delete"},{"name":"GSD_RECOVERY_MODE_TTL","$patch":"delete"}],"volumeMounts":[{"mountPath":"/scripts","$patch":"delete"}]}],"volumes":[{"name":"recovery-script","$patch":"delete"}]}}}}'
   oc rollout status -n $NS deploy/$REL
   oc delete configmap -n $NS $REL-recovery
   ````

   Then verify with §4c.
7. **A sync that is already retrying (the endless retry in **Risks under Argo CD**).** When recovery mode was turned
   on through the values file and the Application's operation reads Running with `Retrying attempt #N`, the pause
   stops new automated syncs but not that operation: Argo CD retries a failed operation whatever the sync policy says,
   up to its `limit`. On the lab, after the pause, retry #2 failed and the operation scheduled retry #3 and stayed
   Running. **Incident step:** pause (step 2), then terminate the operation, from the Application's sync status in the
```

```
   oc rollout status -n $NS deploy/$REL
   ````

   With `selfHeal: true` Argo CD puts both `replicas` back, the recovery Deployment's to 0 and the app's to 1, and
   the app starts on the restored file once the recovery pod is gone. The wait comes first because `oc rollout
   status` run before Argo CD's apply reports the app's Deployment at 0 of 0, already complete. With `selfHeal` off and Git unchanged, automated sync
   does not sync a revision it has already synced ("a second sync will not be attempted, unless `selfHeal` flag is
   set to true"): sync the Application once from Argo CD, and the wait ends when it has (not measured). The
   operator's alternative for a rollback is Argo CD's history and rollback, while still paused (Argo CD refuses it
   while automated sync is on); commit the same values to Git before you end the pause, or automated sync takes the
   release back to what Git says.
6. **Nothing to remove.** The hand edit of step 3 changed only the two `replicas` fields, which Argo CD renders and
   step 5 puts back; the release reads Synced with nothing left over. Verify with §4c.

7. **A sync that is already retrying (the endless retry in **Risks under Argo CD**, a chart before 0.65.0).** When
   recovery mode was turned on through the values file and the Application's operation reads Running with `Retrying attempt #N`, the pause
   stops new automated syncs but not that operation: Argo CD retries a failed operation whatever the sync policy says,
   up to its `limit`. On the lab, after the pause, retry #2 failed and the operation scheduled retry #3 and stayed
   Running. **Incident step:** pause (step 2), then terminate the operation, from the Application's sync status in the
```

<!-- block: docs/CHANGELOG.md | edit -->

```
which `local-development/prepare-release.py` does when the release is cut.

## Unreleased

- **Delete report runs and database copies from the page (#542, `docs/specs/SPEC_H1_gui_cleanup.md`, app 3.1.0,
  chart 0.62.0; `housekeeping.enabled`, on by default).** A cluster administrator (the cluster-admin tier, #322, behind a
```

```
which `local-development/prepare-release.py` does when the release is cut.

## Unreleased

- **Recovery mode is its own workload (#532, `docs/specs/SPEC_E11_recovery_workload.md`, chart 0.65.0).** The chart
  renders a second Deployment, `<fullname>-recovery`, on every release at 0 replicas: the app's pod spec with the
  recovery script, its own labels (no Service, PodDisruptionBudget or ServiceMonitor selects it) and no readiness
  probe. `recovery.enabled: true` in the release's values file now scales the app's Deployment to 0 and the recovery
  Deployment to 1, and `false` the other way round, so both report available, a pipeline that waits for the rollout
  succeeds, and turning recovery mode off takes one rollout, whatever the deployment tool prunes; the 12 min 49 s
  wait behind a retrying sync, measured on the lab, is gone. A required pod anti-affinity on the recovery pod makes
  the scheduler start it only once the app's pod is gone, and the app's only once it is gone, so the two never hold
  the database at once. `restore-db.sh` finds the recovery pod by `app=<release>-recovery` (and `app=<release>` on
  an older chart); its `--list` note on an unmounted `/offsite` and its closing line after a restore no longer
  mislead under the break glass. Runbook §4d's hand edit is two `oc scale` commands, with nothing to remove
  afterwards. Same namespace, ServiceAccount and SCC, no `runAsUser`; no RBAC change (464 rendered lines, none
  removed and none added).

- **Delete report runs and database copies from the page (#542, `docs/specs/SPEC_H1_gui_cleanup.md`, app 3.1.0,
  chart 0.62.0; `housekeeping.enabled`, on by default).** A cluster administrator (the cluster-admin tier, #322, behind a
```

<!-- block: local-development/tests/test_chart_recovery_mode.py | edit -->

```
"""Recovery mode in the chart (#303): `recovery.enabled` swaps the dashboard's command for the
chart's recovery script on the same pod and volume, drops the liveness probe, keeps the pod out of
the Service, and refuses what cannot be safe. Everything else renders as it did.

These shell out to `helm template` because the switch and its guards ARE Helm templating. The
script itself is tested in tests/test_recovery_mode.py.
```

```
"""Recovery mode in the chart (#303), its own workload since #532: a second Deployment renders the app's pod
spec with the chart's recovery script on the same volume, no liveness or readiness probe and labels no Service
selects, at 0 replicas; `recovery.enabled` scales the app's Deployment to 0 and it to 1, and refuses what cannot
be safe. Everything else renders as it did.

These shell out to `helm template` because the switch and its guards ARE Helm templating. The
script itself is tested in tests/test_recovery_mode.py.
```

<!-- block: local-development/tests/test_chart_recovery_mode.py | edit -->

```
from __future__ import annotations

import importlib.util
import pathlib
import re
import shutil
```

```
from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import shutil
```

<!-- block: local-development/tests/test_chart_recovery_mode.py | edit -->

```
CHART = REPO / "charts" / "group-sync-dashboard"
SCRIPT = CHART / "scripts" / "recovery_mode.py"
ON = {"recovery__enabled": "true"}
OFFSITE = {"backup__offsite__enabled": "true"}

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")
```

```
CHART = REPO / "charts" / "group-sync-dashboard"
SCRIPT = CHART / "scripts" / "recovery_mode.py"
ON = {"recovery__enabled": "true"}
APP, REC = "t-group-sync-dashboard", "t-group-sync-dashboard-recovery"
OFFSITE = {"backup__offsite__enabled": "true"}

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")
```

<!-- block: local-development/tests/test_chart_recovery_mode.py | edit -->

```
    return [d for d in yaml.safe_load_all(out) if d]


def _deployment(docs: list[dict]) -> dict:
    return next(d for d in docs if d["kind"] == "Deployment" and d["metadata"]["name"] == "t-group-sync-dashboard")


def _container(docs: list[dict], name: str = "dashboard") -> dict:
    return next(c for c in _deployment(docs)["spec"]["template"]["spec"]["containers"] if c["name"] == name)


def _env(container: dict) -> dict:
```

```
    return [d for d in yaml.safe_load_all(out) if d]


def _deployment(docs: list[dict], name: str = APP) -> dict:
    return next(d for d in docs if d["kind"] == "Deployment" and d["metadata"]["name"] == name)


def _container(docs: list[dict], name: str = "dashboard", workload: str = APP) -> dict:
    return next(c for c in _deployment(docs, workload)["spec"]["template"]["spec"]["containers"] if c["name"] == name)


def _env(container: dict) -> dict:
```

<!-- block: local-development/tests/test_chart_recovery_mode.py | edit -->

```

def test_t303_1_recovery_runs_the_chart_script_on_the_same_volume_with_the_env():
    docs = _docs(**ON)
    dashboard = _container(docs)
    assert dashboard["command"] == ["python3.14", "/scripts/recovery_mode.py", "--release", "t"]
    assert "gsd.api:create_app" not in " ".join(dashboard["command"])
    env = _env(dashboard)
    assert env["GSD_RECOVERY_MODE"] == "true" and env["GSD_RECOVERY_MODE_TTL"] == "2h"
    assert env["GSD_DB_PATH"] == "/data/gsd.db"
    assert _deployment(docs)["spec"]["replicas"] == 1
    data = [m for m in dashboard["volumeMounts"] if m["name"] == "data"]
    assert data == [m for m in _container(_docs())["volumeMounts"] if m["name"] == "data"] == [{"name": "data", "mountPath": "/data"}]
    assert {"name": "recovery-script", "mountPath": "/scripts", "readOnly": True} in dashboard["volumeMounts"]
    assert _env(_container(_docs(recovery__ttl="90m", **ON)))["GSD_RECOVERY_MODE_TTL"] == "90m"


def test_t303_2_recovery_overrides_the_image_cmd_with_the_proxy_off_too():
    docs = _docs(oauthProxy__enabled="false", visibility__enabled="false", reporting__enabled="false", **ON)
    assert _container(docs)["command"][:2] == ["python3.14", "/scripts/recovery_mode.py"]
    off = _container(_docs(oauthProxy__enabled="false", visibility__enabled="false", reporting__enabled="false"))
    assert "command" not in off, "with the proxy off the default render leaves the image's CMD, uvicorn"


def test_t303_3_no_liveness_probe_in_recovery_mode():
    assert "livenessProbe" not in _container(_docs(**ON))
    assert "livenessProbe" in _container(_docs())


@pytest.mark.parametrize("readiness", ["true", "false"])
def test_t303_4_a_readiness_probe_that_cannot_pass_keeps_the_pod_out_of_the_service(readiness):
    dashboard = _container(_docs(probes__readiness__enabled=readiness, **ON))
    assert dashboard["readinessProbe"] == {"tcpSocket": {"port": "http"}, "periodSeconds": 30, "timeoutSeconds": 5,
                                           "failureThreshold": 1}
    # `http` names the dashboard container's own 8080, where nothing listens while the app is stopped.
    assert {"name": "http", "containerPort": 8080} in dashboard["ports"]


def test_t303_5_more_than_one_replica_is_refused():
```

```

def test_t303_1_recovery_runs_the_chart_script_on_the_same_volume_with_the_env():
    docs = _docs(**ON)
    dashboard = _container(docs, workload=REC)
    assert dashboard["command"] == ["python3.14", "/scripts/recovery_mode.py", "--release", "t"]
    assert "gsd.api:create_app" not in " ".join(dashboard["command"])
    env = _env(dashboard)
    assert env["GSD_RECOVERY_MODE"] == "true" and env["GSD_RECOVERY_MODE_TTL"] == "2h"
    assert env["GSD_DB_PATH"] == "/data/gsd.db"
    assert _deployment(docs, REC)["spec"]["replicas"] == 1
    data = [m for m in dashboard["volumeMounts"] if m["name"] == "data"]
    assert data == [m for m in _container(_docs())["volumeMounts"] if m["name"] == "data"] == [{"name": "data", "mountPath": "/data"}]
    assert {"name": "recovery-script", "mountPath": "/scripts", "readOnly": True} in dashboard["volumeMounts"]
    assert _env(_container(_docs(recovery__ttl="90m", **ON), workload=REC))["GSD_RECOVERY_MODE_TTL"] == "90m"


def test_t303_2_recovery_overrides_the_image_cmd_with_the_proxy_off_too():
    docs = _docs(oauthProxy__enabled="false", visibility__enabled="false", reporting__enabled="false", **ON)
    assert _container(docs, workload=REC)["command"][:2] == ["python3.14", "/scripts/recovery_mode.py"]
    off = _container(_docs(oauthProxy__enabled="false", visibility__enabled="false", reporting__enabled="false"))
    assert "command" not in off, "with the proxy off the default render leaves the image's CMD, uvicorn"


def test_t303_3_no_liveness_probe_in_recovery_mode():
    assert "livenessProbe" not in _container(_docs(**ON), workload=REC)
    assert "livenessProbe" in _container(_docs())


@pytest.mark.parametrize("readiness", ["true", "false"])
def test_t532_6_the_recovery_pod_has_no_readiness_probe_and_no_selector_picks_it(readiness):
    """#532 replaced T303-4's readiness probe that could not pass: the recovery pod is kept out of the Service by
    its labels, so it is ready once it runs and its Deployment reports available."""
    docs = _docs(probes__readiness__enabled=readiness, **ON)
    assert "readinessProbe" not in _container(docs, workload=REC)
    assert ("readinessProbe" in _container(docs)) == (readiness == "true"), "the app's probe is as before"


def test_t303_5_more_than_one_replica_is_refused():
```

<!-- block: local-development/tests/test_chart_recovery_mode.py | edit -->

```
    assert "gsd.api:create_app" in dashboard["command"]
    assert "livenessProbe" in dashboard and dashboard["readinessProbe"]["httpGet"]["path"] == "/readyz"
    assert not [k for k in _env(dashboard) if k.startswith("GSD_RECOVERY")]
    assert not [d for d in _docs() if d["metadata"]["name"].endswith("-recovery")]


@pytest.mark.parametrize("extra", [{}, OFFSITE], ids=["default", "offsite"])
def test_t303_15_nothing_but_the_dashboard_container_and_its_volumes_changes(extra):
    off = {_key(d): d for d in _docs(**extra)}
    on = {_key(d): d for d in _docs(**extra, **ON)}
    assert set(on) - set(off) == {("ConfigMap", "t-group-sync-dashboard-recovery")}
    assert set(off) <= set(on)
    changed = [k for k in off if off[k] != on[k]]
    assert changed == [("Deployment", "t-group-sync-dashboard")], changed
    before, after = off[changed[0]], on[changed[0]]
    assert before["metadata"] == after["metadata"]
    spec_before, spec_after = before["spec"]["template"]["spec"], after["spec"]["template"]["spec"]
    assert before["spec"]["template"]["metadata"] == after["spec"]["template"]["metadata"]
    assert [c for c in spec_before["containers"] if c["name"] != "dashboard"] == \
           [c for c in spec_after["containers"] if c["name"] != "dashboard"], "the oauth-proxy sidecar changed"
    assert [v for v in spec_after["volumes"] if v not in spec_before["volumes"]] == \
           [v for v in spec_after["volumes"] if v["name"] in ("recovery-script", "offsite")]
    assert all(v in spec_after["volumes"] for v in spec_before["volumes"])
    for key in ("replicas", "strategy", "selector"):
        assert before["spec"][key] == after["spec"][key]


def test_t303_16_no_rbac_rule_is_added_or_removed():
```

```
    assert "gsd.api:create_app" in dashboard["command"]
    assert "livenessProbe" in dashboard and dashboard["readinessProbe"]["httpGet"]["path"] == "/readyz"
    assert not [k for k in _env(dashboard) if k.startswith("GSD_RECOVERY")]
    # #532: the recovery workload and its script are rendered on every release, the workload at 0 replicas
    assert sorted(_key(d) for d in _docs() if d["metadata"]["name"].endswith("-recovery")) == \
        [("ConfigMap", REC), ("Deployment", REC)]
    assert _deployment(_docs(), REC)["spec"]["replicas"] == 0


@pytest.mark.parametrize("extra", [{}, OFFSITE], ids=["default", "offsite"])
def test_t532_1_the_switch_changes_only_the_two_deployments_replicas(extra):
    """On and off render the same objects and differ in two fields: the app's replicas (1 -> 0) and the recovery
    workload's (0 -> 1). So both report available, and turning it off needs no pruning (#532)."""
    off = {_key(d): d for d in _docs(**extra)}
    on = {_key(d): d for d in _docs(**extra, **ON)}
    assert set(on) == set(off)
    changed = sorted(k for k in off if off[k] != on[k])
    assert changed == [("Deployment", APP), ("Deployment", REC)], changed
    assert (off[("Deployment", APP)]["spec"]["replicas"], on[("Deployment", APP)]["spec"]["replicas"]) == (1, 0)
    assert (off[("Deployment", REC)]["spec"]["replicas"], on[("Deployment", REC)]["spec"]["replicas"]) == (0, 1)
    for key in changed:
        before, after = off[key], on[key]
        before["spec"].pop("replicas"), after["spec"].pop("replicas")
        assert before == after, key


def test_t532_1_the_recovery_pod_is_the_app_pod_with_the_recovery_branches():
    """The recovery workload's pod spec is the app's except for the dashboard container's command, env, mounts and
    probes, the recovery volumes and the anti-affinity: the oauth-proxy sidecar and everything else are the same."""
    docs = _docs(**OFFSITE)
    app, rec = (_deployment(docs, n)["spec"]["template"]["spec"] for n in (APP, REC))
    assert [c for c in app["containers"] if c["name"] != "dashboard"] == \
           [c for c in rec["containers"] if c["name"] != "dashboard"], "the oauth-proxy sidecar differs"
    assert [v for v in rec["volumes"] if v not in app["volumes"]] == \
           [v for v in rec["volumes"] if v["name"] in ("recovery-script", "offsite")]
    assert all(v in rec["volumes"] for v in app["volumes"])
    rest = lambda pod: {k: v for k, v in pod.items() if k not in ("containers", "volumes", "affinity")}
    assert rest(app) == rest(rec)
    assert _deployment(docs, REC)["spec"]["strategy"] == _deployment(docs)["spec"]["strategy"] == {"type": "Recreate"}


def test_t532_2_no_selector_of_the_app_picks_the_recovery_pod_and_back():
    """The Service, the PodDisruptionBudget, the ServiceMonitor's Service and the app's Deployment select the app's
    pod only; the recovery Deployment selects its own pod only; the report service's NetworkPolicy admits the
    app's pod only (#532)."""
    docs = _docs(**ON)
    pod_labels = {n: _deployment(docs, n)["spec"]["template"]["metadata"]["labels"] for n in (APP, REC)}
    picks = lambda selector, labels: all(labels.get(k) == v for k, v in selector.items())
    service = next(d for d in docs if _key(d) == ("Service", APP))["spec"]["selector"]
    pdb = next(d for d in docs if d["kind"] == "PodDisruptionBudget" and d["metadata"]["name"] == APP)
    selectors = {"Service": service, "PodDisruptionBudget": pdb["spec"]["selector"]["matchLabels"],
                 "app Deployment": _deployment(docs)["spec"]["selector"]["matchLabels"]}
    netpol = next(d for d in docs if d["kind"] == "NetworkPolicy")
    selectors["report NetworkPolicy"] = next(p["podSelector"]["matchLabels"] for rule in netpol["spec"]["ingress"]
                                            for p in rule.get("from", []) if "podSelector" in p
                                            and p["podSelector"].get("matchLabels", {}).get("app") == APP)
    for name, selector in selectors.items():
        assert picks(selector, pod_labels[APP]) and not picks(selector, pod_labels[REC]), name
    recovery = _deployment(docs, REC)["spec"]["selector"]["matchLabels"]
    assert picks(recovery, pod_labels[REC]) and not picks(recovery, pod_labels[APP])
    assert pod_labels[REC]["app"] == REC, "restore-db.sh finds the recovery pod by app=<release>-recovery"


def test_t532_3_the_recovery_pod_waits_for_the_app_pod_and_holds_it_back_cluster_wide():
    """One required anti-affinity term on the recovery pod: no app pod anywhere on a node of the same OS (every
    node this image runs on), appended to the values' affinity; the app pod's affinity is the values' alone."""
    term = {"labelSelector": {"matchLabels": {"app": APP, "app.kubernetes.io/instance": "t",
                                              "app.kubernetes.io/name": "group-sync-dashboard"}},
            "topologyKey": "kubernetes.io/os"}
    docs = _docs(**ON)
    assert _deployment(docs, REC)["spec"]["template"]["spec"]["affinity"] == \
        {"podAntiAffinity": {"requiredDuringSchedulingIgnoredDuringExecution": [term]}}
    assert "affinity" not in _deployment(docs)["spec"]["template"]["spec"]
    zone = {"key": "topology.kubernetes.io/zone", "operator": "In", "values": ["a"]}
    mine = {"labelSelector": {"matchLabels": {"x": "y"}}, "topologyKey": "kubernetes.io/hostname"}
    ok, out = render("--set-json", 'affinity={"nodeAffinity":{"requiredDuringSchedulingIgnoredDuringExecution":'
                     '{"nodeSelectorTerms":[{"matchExpressions":[' + json.dumps(zone) + ']}]}},'
                     '"podAntiAffinity":{"requiredDuringSchedulingIgnoredDuringExecution":[' + json.dumps(mine) + ']}}',
                     **ON)
    assert ok, out
    docs = [d for d in yaml.safe_load_all(out) if d]
    app, rec = (_deployment(docs, n)["spec"]["template"]["spec"]["affinity"] for n in (APP, REC))
    assert app["podAntiAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"] == [mine]
    assert rec["podAntiAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"] == [mine, term]
    assert rec["nodeAffinity"] == app["nodeAffinity"]


def test_t532_4_same_serviceaccount_and_security_context_and_no_uid_of_its_own():
    """The operator's decision on #532: the same namespace, ServiceAccount and SCC, and no runAsUser, so OpenShift
    assigns the recovery pod the UID it assigns the app's (restricted-v2's range)."""
    docs = _docs(**ON)
    app, rec = (_deployment(docs, n) for n in (APP, REC))
    assert rec["metadata"]["namespace"] == app["metadata"]["namespace"]
    pa, pr = app["spec"]["template"]["spec"], rec["spec"]["template"]["spec"]
    assert pr["serviceAccountName"] == pa["serviceAccountName"] == APP
    assert pr["securityContext"] == pa["securityContext"] and "runAsUser" not in pr["securityContext"]
    for container in pr["containers"]:
        assert "runAsUser" not in (container.get("securityContext") or {}), container["name"]
    assert _container(docs, workload=REC)["securityContext"] == _container(docs)["securityContext"]


def test_t303_16_no_rbac_rule_is_added_or_removed():
```

<!-- block: local-development/tests/test_chart_recovery_mode.py | edit -->

```
    cm = next(d for d in _docs(**ON) if _key(d) == ("ConfigMap", "t-group-sync-dashboard-recovery"))
    assert cm["data"]["recovery_mode.py"].strip() == SCRIPT.read_text().strip()
    assert cm["metadata"]["labels"]["app.kubernetes.io/component"] == "recovery"
    volume = next(v for v in _deployment(_docs(**ON))["spec"]["template"]["spec"]["volumes"] if v["name"] == "recovery-script")
    assert volume == {"name": "recovery-script", "configMap": {"name": "t-group-sync-dashboard-recovery", "defaultMode": 0o444}}


@pytest.mark.parametrize("claim,expected", [("", "t-group-sync-dashboard-backup-offsite"), ("my-offsite", "my-offsite")])
def test_the_offsite_claim_is_mounted_read_only_as_the_cronjob_names_it(claim, expected):
    docs = _docs(backup__offsite__destination__pvc__existingClaim=claim, **OFFSITE, **ON)
    pod = _deployment(docs)["spec"]["template"]["spec"]
    assert {"name": "offsite", "persistentVolumeClaim": {"claimName": expected, "readOnly": True}} in pod["volumes"]
    assert {"name": "offsite", "mountPath": "/offsite", "readOnly": True} in _container(docs)["volumeMounts"]
    cronjob = next(d for d in docs if d["kind"] == "CronJob")
    shipped = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]["volumes"]
    assert {"name": "offsite", "persistentVolumeClaim": {"claimName": expected}} in shipped


S3 = {"backup__offsite__destination__type": "s3", "backup__offsite__destination__s3__existingSecret": "creds",
```

```
    cm = next(d for d in _docs(**ON) if _key(d) == ("ConfigMap", "t-group-sync-dashboard-recovery"))
    assert cm["data"]["recovery_mode.py"].strip() == SCRIPT.read_text().strip()
    assert cm["metadata"]["labels"]["app.kubernetes.io/component"] == "recovery"
    volume = next(v for v in _deployment(_docs(**ON), REC)["spec"]["template"]["spec"]["volumes"] if v["name"] == "recovery-script")
    assert volume == {"name": "recovery-script", "configMap": {"name": "t-group-sync-dashboard-recovery", "defaultMode": 0o444}}


@pytest.mark.parametrize("claim,expected", [("", "t-group-sync-dashboard-backup-offsite"), ("my-offsite", "my-offsite")])
def test_the_offsite_claim_is_mounted_read_only_as_the_cronjob_names_it(claim, expected):
    docs = _docs(backup__offsite__destination__pvc__existingClaim=claim, **OFFSITE, **ON)
    pod = _deployment(docs, REC)["spec"]["template"]["spec"]
    assert {"name": "offsite", "persistentVolumeClaim": {"claimName": expected, "readOnly": True}} in pod["volumes"]
    assert {"name": "offsite", "mountPath": "/offsite", "readOnly": True} in _container(docs, workload=REC)["volumeMounts"]
    cronjob = next(d for d in docs if d["kind"] == "CronJob")
    shipped = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]["volumes"]
    assert {"name": "offsite", "persistentVolumeClaim": {"claimName": expected}} in shipped


def test_t532_5_on_a_single_node_claim_the_offsite_copy_runs_beside_either_workloads_pod():
    """On ReadWriteOnce the offsite Job must run on the node that holds the data claim: beside the app's pod, or in
    recovery mode the recovery pod's, as it did when the recovery pod carried the app's labels (#532)."""
    docs = _docs(persistence__accessMode="ReadWriteOnce", reporting__enabled="false", **OFFSITE, **ON)
    cronjob = next(d for d in docs if d["kind"] == "CronJob" and d["metadata"]["name"].endswith("-backup-offsite"))
    (term,) = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]["affinity"]["podAffinity"][
        "requiredDuringSchedulingIgnoredDuringExecution"]
    assert term["topologyKey"] == "kubernetes.io/hostname"
    selector = term["labelSelector"]

    def picks(labels: dict) -> bool:
        return (all(labels.get(k) == v for k, v in selector["matchLabels"].items())
                and all(labels.get(e["key"]) in e["values"] for e in selector["matchExpressions"]))

    for name in (APP, REC):
        assert picks(_deployment(docs, name)["spec"]["template"]["metadata"]["labels"]), name
    job_labels = cronjob["spec"]["jobTemplate"]["spec"]["template"]["metadata"]["labels"]
    assert not picks(job_labels)


S3 = {"backup__offsite__destination__type": "s3", "backup__offsite__destination__s3__existingSecret": "creds",
```

<!-- block: local-development/tests/test_chart_recovery_mode.py | edit -->

```
    them, the recovery pod mounts the claim the CronJob writes, and nothing when it writes none. A default
    that turns offsite on (#304) must turn the mount on with it, or this test fails."""
    docs = _docs(**extra, **ON)
    mounted = [v["persistentVolumeClaim"]["claimName"] for v in _deployment(docs)["spec"]["template"]["spec"]["volumes"]
               if v["name"] == "offsite"]
    written = [v["persistentVolumeClaim"]["claimName"] for d in docs if d["kind"] == "CronJob"
               for v in d["spec"]["jobTemplate"]["spec"]["template"]["spec"]["volumes"]
```

```
    them, the recovery pod mounts the claim the CronJob writes, and nothing when it writes none. A default
    that turns offsite on (#304) must turn the mount on with it, or this test fails."""
    docs = _docs(**extra, **ON)
    mounted = [v["persistentVolumeClaim"]["claimName"] for v in _deployment(docs, REC)["spec"]["template"]["spec"]["volumes"]
               if v["name"] == "offsite"]
    written = [v["persistentVolumeClaim"]["claimName"] for d in docs if d["kind"] == "CronJob"
               for v in d["spec"]["jobTemplate"]["spec"]["template"]["spec"]["volumes"]
```

<!-- block: local-development/tests/test_chart_recovery_mode.py | edit -->

```
    assert "GroupSyncDashboardNotPolling does not fire" in comment
    assert "GroupSyncDashboardReportSnapshotStale" in comment and "The TTL is the bound" in comment
    # what the TTL ends (measured: an exec'd process is killed when PID 1 exits) and what restarts it
    assert "every process in the container stops" in comment and "evicted" in comment and "0/1" in comment
    runbook = (REPO / "docs" / "RUNBOOK_backup_restore.md").read_text()
    assert "Check the time left first" in runbook and "every process in the container stops" in runbook
    for doc in (CHART / "README.md", REPO / "docs" / "RUNBOOK_backup_restore.md", CHART / "values.yaml"):
```

```
    assert "GroupSyncDashboardNotPolling does not fire" in comment
    assert "GroupSyncDashboardReportSnapshotStale" in comment and "The TTL is the bound" in comment
    # what the TTL ends (measured: an exec'd process is killed when PID 1 exits) and what restarts it
    assert "every process in the container stops" in comment and "evicted" in comment and "1/1" in comment
    runbook = (REPO / "docs" / "RUNBOOK_backup_restore.md").read_text()
    assert "Check the time left first" in runbook and "every process in the container stops" in runbook
    for doc in (CHART / "README.md", REPO / "docs" / "RUNBOOK_backup_restore.md", CHART / "values.yaml"):
```

<!-- block: local-development/tests/test_chart_backup_offsite.py | edit -->

```
        (term,) = pod["spec"]["affinity"]["podAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"]
        assert term["topologyKey"] == "kubernetes.io/hostname"
        selector = [d for d in docs if d.get("kind") == "Service"][0]["spec"]["selector"]
        assert term["labelSelector"]["matchLabels"] == selector

    def test_rwop_is_refused(self):
        ok, out = render(**ON, persistence__accessMode="ReadWriteOncePod", reporting__enabled="false")   # reporting refuses RWOP first (C3)
```

```
        (term,) = pod["spec"]["affinity"]["podAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"]
        assert term["topologyKey"] == "kubernetes.io/hostname"
        selector = [d for d in docs if d.get("kind") == "Service"][0]["spec"]["selector"]
        # #532: the term picks the app's pod (the Service's selector) or, in recovery mode, the recovery workload's
        labels = term["labelSelector"]
        assert labels["matchLabels"] == {k: v for k, v in selector.items() if k != "app"}
        assert labels["matchExpressions"] == [{"key": "app", "operator": "In",
                                               "values": [selector["app"], selector["app"] + "-recovery"]}]

    def test_rwop_is_refused(self):
        ok, out = render(**ON, persistence__accessMode="ReadWriteOncePod", reporting__enabled="false")   # reporting refuses RWOP first (C3)
```

<!-- block: local-development/tests/test_restore_db_wrapper.py | edit -->

```
    assert [c for c in calls(lab) if c.startswith("exec")] == []


@pytest.mark.parametrize("n", [0, 2])
def test_t302_5_none_or_two_pods_are_refused_before_any_exec(lab, n: int) -> None:
    result = lab("--from-version", f"{KNOWN}-{STAMPS[0]}", "--yes", pod_list=pods(RECOVERY, n=n))
```

```
    assert [c for c in calls(lab) if c.startswith("exec")] == []


def test_t532_7_the_pods_are_listed_from_both_workloads(lab) -> None:
    """The recovery pod is app=<release>-recovery from chart 0.65.0 and app=<release> before it; both are listed,
    so an app pod still terminating beside the recovery pod makes two and is refused (#532)."""
    lab("--list", pod_list=pods(RECOVERY))
    (listed,) = [c for c in calls(lab) if c.startswith("get pods")]
    assert "-l app in (group-sync-dashboard,group-sync-dashboard-recovery)" in listed, listed


@pytest.mark.parametrize("n", [0, 2])
def test_t302_5_none_or_two_pods_are_refused_before_any_exec(lab, n: int) -> None:
    result = lab("--from-version", f"{KNOWN}-{STAMPS[0]}", "--yes", pod_list=pods(RECOVERY, n=n))
```

<!-- block: local-development/tests/test_restore_db.py | edit -->

```
    assert re.search(r"\s+offsite\s+ok\s+yes$", row(result, f"{KNOWN}-{STAMPS[3]}"))
    assert f"live     {pod.db} · user_version {KNOWN}" in result.stdout
    assert f"image    understands schema {KNOWN} and older" in result.stdout


def test_t302_2_a_byte_identical_offsite_twin_is_one_row_and_a_differing_one_is_refused(pod: Pod) -> None:
```

```
    assert re.search(r"\s+offsite\s+ok\s+yes$", row(result, f"{KNOWN}-{STAMPS[3]}"))
    assert f"live     {pod.db} · user_version {KNOWN}" in result.stdout
    assert f"image    understands schema {KNOWN} and older" in result.stdout


def test_t532_8_the_two_messages_say_what_is_true_under_the_break_glass_too(pod: Pod) -> None:
    """SPEC_E10's walk, O1 (#532): an unmounted /offsite is the pod's mount, not the backup destination, and the
    line after a restore names both ways recovery mode was turned on, the values file and §4d's give-back."""
    shutil.rmtree(pod.offsite)
    listed = pod.run("list")
    assert listed.returncode == 0, listed.stderr
    note = " ".join(line for line in listed.stdout.splitlines() if line.startswith("# offsite:"))
    assert "is not mounted in this pod" in note and "when backup.offsite uses its pvc destination" in note
    assert "section 4b" in note and "only when" not in note
    restored = pod.run("restore", f"{KNOWN}-{STAMPS[0]}")
    assert restored.returncode == 0, restored.stderr
    closing = " ".join(restored.stdout.split())
    assert "set recovery.enabled: false in this release's values file" in closing
    assert "section 4d), give the release back to Git (its step 5)" in closing
    assert "once the recovery pod is gone" in closing


def test_t302_2_a_byte_identical_offsite_twin_is_one_row_and_a_differing_one_is_refused(pod: Pod) -> None:
```

<!-- block: local-development/tests/test_runbook_backup_restore.py | edit -->

```
    assert "--namespace $NS --release $REL" in body, "the script defaults to group-sync-dashboard for both; the runbook's NS is not it"
    code = code_lines(body)
    assert any(line.startswith("oc debug -n $NS deploy/$REL") for line in code), "the fallback keeps oc debug"
    assert not [line for line in code if line.startswith("oc scale")], "no oc scale in §4's commands"
    assert "`replicaCount: 0` in this release's values file" in body
    # the only Helm command line is the one labelled for development and troubleshooting; the break glass (§4d, the
    # last subsection) and the risks box it answers are the one place where Argo CD's controls and hand edits are the
```

```
    assert "--namespace $NS --release $REL" in body, "the script defaults to group-sync-dashboard for both; the runbook's NS is not it"
    code = code_lines(body)
    assert any(line.startswith("oc debug -n $NS deploy/$REL") for line in code), "the fallback keeps oc debug"
    # the break glass (§4d) scales the two Deployments by hand since #532; nothing else in §4 does
    outside = code_lines(body.split("### 4d.", 1)[0])
    assert not [line for line in outside if line.startswith("oc scale")], "no oc scale in §4's commands outside §4d"
    assert "`replicaCount: 0` in this release's values file" in body
    # the only Helm command line is the one labelled for development and troubleshooting; the break glass (§4d, the
    # last subsection) and the risks box it answers are the one place where Argo CD's controls and hand edits are the
```

<!-- block: local-development/tests/test_runbook_backup_restore.py | edit -->

```
        assert words in risks, words
    step5 = flat(body.split("5. **Turn it off**", 1)[1].split("\n\n", 1)[0])
    assert "stops at once" not in step5, "under a retrying sync the recovery pod does not stop at once (#532)"
    for words in ("#532", "12 min 49 s", "known limitation"):
        assert words in step5, words


def test_t533_6_section_4d_pauses_first_and_gives_the_release_back_to_git() -> None:
```

```
        assert words in risks, words
    step5 = flat(body.split("5. **Turn it off**", 1)[1].split("\n\n", 1)[0])
    assert "stops at once" not in step5, "under a retrying sync the recovery pod does not stop at once (#532)"
    # #532 (SPEC_E11): from chart 0.65.0 the switch takes one rollout; the measured wait is for older charts
    for words in ("#532", "within the one rollout", "On a chart before 0.65.0", "12 min 49 s"):
        assert words in step5, words
    assert "nothing to retry" in risks and "endless retry, on a chart before 0.65.0" in risks


def test_t533_6_section_4d_pauses_first_and_gives_the_release_back_to_git() -> None:
```

<!-- block: local-development/tests/test_runbook_backup_restore.py | edit -->

```
        "{.metadata.ownerReferences[*].kind}",
        """--type merge -p '{"spec":{"syncPolicy":{"automated":{"enabled":false}}}}'""",
        "{.spec.syncPolicy.automated.enabled} {.status.operationState.phase}",
        "oc create configmap -n $NS $REL-recovery",
        '"command":["python3.14","/scripts/recovery_mode.py"',
        "restore-db.sh --list",
        '[{"op":"remove","path":"/spec/syncPolicy/automated/enabled"}]',
        "--for=jsonpath='{.status.sync.status}'=Synced",
        "oc rollout status -n $NS deploy/$REL",
        '"$patch":"delete"',
        "oc delete configmap -n $NS $REL-recovery",
        "argocd app terminate-op $APP",
    ]
    where = []
```

```
        "{.metadata.ownerReferences[*].kind}",
        """--type merge -p '{"spec":{"syncPolicy":{"automated":{"enabled":false}}}}'""",
        "{.spec.syncPolicy.automated.enabled} {.status.operationState.phase}",
        "oc scale -n $NS deploy/$REL --replicas=0",
        "oc scale -n $NS deploy/$REL-recovery --replicas=1",
        "restore-db.sh --list",
        '[{"op":"remove","path":"/spec/syncPolicy/automated/enabled"}]',
        "--for=jsonpath='{.status.sync.status}'=Synced",
        "oc rollout status -n $NS deploy/$REL",
        "argocd app terminate-op $APP",
    ]
    where = []
```

<!-- block: local-development/tests/test_runbook_backup_restore.py | edit -->

```
        assert hits, f"§4d prints no command with {step!r}"
        where.append(hits[0])
    assert where == sorted(where), "§4d's commands are out of order"
    # the give-back's rollout status comes after the wait for Synced: before Argo CD's apply it reports the recovery
    # rollout, which never completed, and after the progress deadline it fails at once (measured on the lab)
    assert where[steps.index("--for=jsonpath='{.status.sync.status}'=Synced")] < where[steps.index("oc rollout status -n $NS deploy/$REL")]
    prose = flat(glass)
    for words in ("ignoreApplicationDifferences", "uvicorn is running here", "Incident step", "selfHeal", "0 of 163",
                  "a phase that is not `Running`", "each retry applies what Git renders over the hand edit",
                  "exceeded its progress deadline"):
        assert words in prose, words
    # the §5 walk (2026-10-02) ran the restore and step 7; without an Argo CD login the CLI needs its --core form
    assert "Not measured on the lab" not in prose and "except the restore itself" not in prose
    for words in ("argocd --core", 'configmap "argocd-cm" not found', "Operation terminated (retried 3 times)", "5m44s"):
```

```
        assert hits, f"§4d prints no command with {step!r}"
        where.append(hits[0])
    assert where == sorted(where), "§4d's commands are out of order"
    # the give-back's rollout status comes after the wait for Synced: before Argo CD's apply it reports the app's
    # Deployment at 0 of 0, already complete (#532)
    assert where[steps.index("--for=jsonpath='{.status.sync.status}'=Synced")] < where[steps.index("oc rollout status -n $NS deploy/$REL")]
    prose = flat(glass)
    for words in ("ignoreApplicationDifferences", "Incident step", "selfHeal", "Nothing to remove",
                  "a phase that is not `Running`", "each retry applies what Git renders over the hand edit",
                  "0 of 0, already complete", "a chart before 0.65.0"):
        assert words in prose, words
    assert "oc patch -n $NS deploy" not in glass and "helm pull" not in glass, "the hand edit is two oc scale commands"
    # the §5 walk (2026-10-02) ran the restore and step 7; without an Argo CD login the CLI needs its --core form
    assert "Not measured on the lab" not in prose and "except the restore itself" not in prose
    for words in ("argocd --core", 'configmap "argocd-cm" not found', "Operation terminated (retried 3 times)", "5m44s"):
```

<!-- block: local-development/tests/test_runbook_backup_restore.py | edit -->

```


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")
def test_t533_7_the_hand_edit_is_what_recovery_mode_renders_and_the_removal_takes_back_what_it_added() -> None:
    """§4d's hand edit must be the chart's recovery mode for the dashboard container, or the pod it makes is not the
    recovery pod `restore-db.sh` and SPEC_E2 promise; and step 6 must remove exactly what it added, because Argo CD
    leaves every field it does not render (SPEC_E10 §2.10)."""
    glass = section("4").split("### 4d.", 1)[1]
    prefix = "oc patch -n $NS deploy/$REL --type strategic -p '"
    patches = [line[len(prefix):].rsplit("'", 1)[0] for line in code_lines(glass) if line.startswith(prefix)]
    assert len(patches) == 2, patches
    add, remove = (json.loads(p.replace("'$REL'", "group-sync-dashboard").replace("'$TTL'", "2h")) for p in patches)

    def dashboard(*flags: str) -> tuple[dict, dict]:
        out = subprocess.run(["helm", "template", "group-sync-dashboard", str(REPO / "charts" / "group-sync-dashboard"),
                              "--set", "ingress.host=t.example.com", *flags],
                             capture_output=True, text=True, check=True).stdout
        pod = next(d for d in yaml.safe_load_all(out) if d and d["kind"] == "Deployment"
                   and d["metadata"]["name"] == "group-sync-dashboard")["spec"]["template"]["spec"]
        return pod, next(c for c in pod["containers"] if c["name"] == "dashboard")

    recovery_pod, recovery = dashboard("--set", "recovery.enabled=true")
    normal_pod, normal = dashboard()
    edit_pod = add["spec"]["template"]["spec"]
    edit = edit_pod["containers"][0]
    assert edit["name"] == "dashboard" and edit["command"] == recovery["command"]
    assert edit["livenessProbe"] is None and "livenessProbe" not in recovery and "livenessProbe" in normal
    rendered = {e["name"]: e.get("value") for e in recovery["env"]}
    assert {e["name"]: e["value"] for e in edit["env"]} == {n: rendered[n] for n in ("GSD_RECOVERY_MODE", "GSD_RECOVERY_MODE_TTL")}
    assert edit["volumeMounts"] == [m for m in recovery["volumeMounts"] if m["mountPath"] == "/scripts"]
    assert edit_pod["volumes"] == [v for v in recovery_pod["volumes"] if v["name"] == "recovery-script"]
    # what the edit adds is not in the normal render, so Argo CD never takes it away: only step 6 does
    assert not {e["name"] for e in edit["env"]} & {e["name"] for e in normal["env"]}
    assert "/scripts" not in {m["mountPath"] for m in normal["volumeMounts"]}
    assert "recovery-script" not in {v["name"] for v in normal_pod["volumes"]}
    undo_pod = remove["spec"]["template"]["spec"]
    undo = undo_pod["containers"][0]
    assert undo["name"] == "dashboard"
    assert all(item.get("$patch") == "delete" for item in [*undo["env"], *undo["volumeMounts"], *undo_pod["volumes"]])
    assert {e["name"] for e in undo["env"]} == {e["name"] for e in edit["env"]}
    assert {m["mountPath"] for m in undo["volumeMounts"]} == {m["mountPath"] for m in edit["volumeMounts"]}
    assert {v["name"] for v in undo_pod["volumes"]} == {v["name"] for v in edit_pod["volumes"]}
```

```


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")
def test_t533_7_the_hand_edit_is_what_recovery_mode_renders() -> None:
    """§4d's hand edit must be the chart's recovery mode, or the pod it makes is not the recovery pod `restore-db.sh`
    and SPEC_E2 promise. Since #532 (SPEC_E11) it is two `oc scale` commands: applied to the default render they
    give exactly the render with recovery.enabled: true, so Argo CD's give-back (step 5) leaves nothing behind."""
    glass = section("4").split("### 4d.", 1)[1]
    scale = re.compile(r"^oc scale -n \$NS deploy/\$REL(?P<suffix>-recovery)? --replicas=(?P<n>\d)$")
    scaled = {"group-sync-dashboard" + (m.group("suffix") or ""): int(m.group("n"))
              for m in map(scale.match, code_lines(glass)) if m}
    assert len(scaled) == 2 and len([line for line in code_lines(glass) if line.startswith("oc scale")]) == 2, scaled

    def deployments(*flags: str) -> dict:
        out = subprocess.run(["helm", "template", "group-sync-dashboard", str(REPO / "charts" / "group-sync-dashboard"),
                              "--set", "ingress.host=t.example.com", *flags],
                             capture_output=True, text=True, check=True).stdout
        return {d["metadata"]["name"]: d for d in yaml.safe_load_all(out) if d and d["kind"] == "Deployment"}

    by_hand, rendered = deployments(), deployments("--set", "recovery.enabled=true")
    for name, replicas in scaled.items():
        by_hand[name]["spec"]["replicas"] = replicas
    assert by_hand == rendered
```
