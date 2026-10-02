# SPEC E10 — the backup runbook corrected from the #300 walk, and a break glass under Argo CD (#533, #532)

| | |
|---|---|
| Programme | Epic E (#385), restore tools and release safety; the last child before Epic E's 3.0.0 release. It corrects what the SPEC_E7 §5 walk (#300, `reports/2026-10-02_runbook-schema-line-300/`) found wrong in the merged runbook and in SPEC_E7, states #532's delay as a known limitation (the operator's decision of 2026-10-02, on #532), and adds the break glass the operator asked for the same day |
| Batch | E — restore tools and release safety |
| Release | — (post-programme; Epic E's release, milestone 3.0.0) |
| Version on release | no version change (docs, a repository tool and tests) |
| Version note | The blocks touch `docs/`, `local-development/prepare-release.py` and `local-development/tests/`, none of them in `publish.yml`'s image paths, and nothing under `charts/`; `check-app-version-bump.py` measured on the applied tree says "no image content changed" (§4.3) |
| Issue | [#533](https://github.com/ephico2real2/group-sync-dashboard/issues/533) |
| Status | specified |
| Source | OB1-lite's research and specification of 2026-10-02, written before any code from #533's body, #532's body and comment, the walk record (README findings F1–F6, `walk.log`) and the operator's two amendments of the same day relayed by the orchestrator (Orchestrator's notes, 1). Measured on origin/main `521c2bb0` (application 2.4.0, chart 0.61.2) with `oc` 4.22.13, helm v4.3.0 and Python 3.14, and on the CRC lab (OpenShift 4.22.7, OpenShift GitOps 1.21.4, Argo CD v3.4.7): one `oc debug --one-container` run, read-only reads, and the break-glass walk up to `restore-db.sh --list` with the lab put back as it was (§2.10). §7's blocks were proved on a throwaway tree of `521c2bb0` (§4.3) |

## How to read this spec

**The point in one sentence: the backup runbook's four instructions that failed when the #300 walk ran them as printed
are corrected (§4a's `oc debug` never returned, §4c's counts cannot match once the app polls, §0 named gauges without
a command, SPEC_E7 said a restore left the database unchanged), §4 now opens with the two risks Argo CD brings to a
restore, and a new §4d is the break glass for an incident under Argo CD: pause its automated sync, put the pod into
recovery mode by hand, restore with the script, give the release back to Git.**

§1 is the mandate. §2 is the research: each source with the sentence relied on, and every lab command with its output.
§2a lists the alternatives and maps each external claim to the line of this repository that behaves accordingly. §3
is the design, with the safety budgets. §4 is one test per change (T533-1 to T533-8), each shown failing without the
change. §5 is the walk the implementing pull request runs. §6 is what an operator sees. §7 is the whole change as
implementation blocks (`docs/specs/README.md`, "Implementation blocks"), applied with

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_E10_runbook_corrections.md . --apply

## Orchestrator's notes

1. **The scope was amended twice on 2026-10-02, by the operator, relayed by the orchestrator.** The first mandate said
   the values-file path only for #532. Then, verbatim: *"Argocd is automated and it had a feature that humans can
   always override. In this I would preferred we pause argocd. As part run book then edit the deployment manually and
   change the env for recovery mode and let the application be restored. Then update values.yaml in git to match the
   working version or rollback using argocd."* And: *"note the risk if argocd is on and the endless retry"*, as a
   short Risks box at the top of §4. So §4d is a break glass that names Argo CD's own controls and hand edits, and
   the values-file rule (`docs/specs/SPEC_E2_recovery_mode.md`, Orchestrator's notes, the operator's direction of 2026-10-01; held by `local-development/tests/test_chart_recovery_mode.py#test_the_only_documented_path_is_the_values_file`) still governs every
   other line of §4: `test_t300_10` keeps its prohibitions for §4 and exempts exactly the Risks box and §4d (block 16).
2. **The operator's "change the env for recovery mode" is not enough, measured; the hand edit is the chart's own
   recovery render.** `oc set env … GSD_RECOVERY_MODE=true GSD_RECOVERY_MODE_TTL=2h` with Argo CD paused restarted
   the pod with the app still running (`2/2`), and `restore-db.sh --list` refused: `uvicorn is running here (pid 1)`
   (§2.10, phase 3). The app reads neither variable (`grep -rn GSD_RECOVERY local-development/gsd/`: nothing). What
   stops the app is the command: the chart's recovery render (`charts/group-sync-dashboard/templates/deployment.yaml#RECOVERY MODE (#303)`)
   runs `/scripts/recovery_mode.py` from a ConfigMap rendered only while `recovery.enabled` is true, and drops the
   liveness probe. §4d step 3 creates that ConfigMap from the chart the release runs and applies one strategic patch
   with exactly the render's command, variables, mount and volume (T533-7 holds them equal to `helm template`).
   **Open question for the operator, not in this spec:** whether the chart should always ship the recovery script
   and have the container honour `GSD_RECOVERY_MODE`, so that the break glass becomes the one variable the operator
   expected. That is a chart and image change; this spec is documentation.
3. **Argo CD does not undo a hand edit's added fields, measured.** The lab's Application syncs with
   `ServerSideApply=true`. After the pause was lifted, Argo CD put back the fields it renders (the command and the
   liveness probe, 2.6 s) and read Synced while the two variables, the `/scripts` mount and its volume stayed: 10
   field differences from the pre-incident pod template (§2.10, phase 5). Kubernetes says why: a field removed from
   an applied manifest is deleted only "if the field is not owned by any other field managers" (§2.7). §4d step 6
   removes them with one more patch; after it the template equals the pre-incident one (0 of 163 fields differ,
   phase 6). The same mechanism is risk 1's half-revert (§2.10, phases 1 and 1b).
4. **#532 stays open.** The operator decided on 2026-10-02 that 3.0.0 ships with #532 as a documented known limitation
   and that its research, spec and fix follow the release. This spec states the delay where the operator reads it
   (§4 step 5 and the Risks box) and in the CHANGELOG entry, and adds the way out (§4d step 7). For #532's own
   research: Argo CD v3.4.7 has `syncPolicy.retry.refresh` ("the latest revision should be used on retry instead of
   the initial one", §2.6), an Application setting; whether recovery mode can report something Argo CD does not wait
   on is #532's other option. Neither is decided here.
5. **Found while specifying: `prepare-release.py` cannot read a two-digit spec id, and the 3.0.0 cut would refuse.**
   `_INDEX_MERGED` matches `[A-Z]\d[a-z]?` (`local-development/prepare-release.py#_INDEX_MERGED`), so once E10's row
   and header read `merged`, `promote_merged_specs` finds the header and not the row and raises "header Status is
   merged but the index is not: ['SPEC_E10_runbook_corrections.md']". Block 18 widens the id to `\d+` and blocks 19 and
   20 add the case to the existing promotion test. `test_specs_index.py#INDEX_ROW` has the same pattern; it is
   corrected in this spec's own commit, with the row, because without it the index tests fail on the row itself.
6. **E10's exclusion from the rising-number assert.** #533 is the highest issue in the index, so E10's row would pass
   that assert without an exclusion; it is excluded by its id and pinned to #533 as the mandate says, the same narrow
   way as E2–W1, so a later row for a lower number (#532's spec) does not need E10's line changed, and a mistyped
   issue on E10's row and header still fails.
7. **Not run, by instruction or for want of the case.** The restore itself was not run in the break-glass walk (the
   orchestrator: stop at "`restore-db.sh --list` accepts the pod"); the restore reads the TTL record the recovery
   script writes at its start (`charts/group-sync-dashboard/scripts/recovery_mode.py#STATE_NAME`), and the script ran
   (its `RECOVERY MODE` and `TTL 2h` lines). The lab has no ApplicationSet (`oc get applicationset -A`: none), so the
   ApplicationSet case is from Argo CD's documentation. Terminating a retrying operation needs one, that is recovery
   turned on through the pipeline; it is from Argo CD's documentation and source. §5 lists what the implementing pull
   request walks.
8. **The hand edit does not mount the offsite claim.** The chart's recovery render mounts `/offsite` read-only when
   `backup.offsite` uses its `pvc` destination; the break glass keeps its patch to what stopping the app needs, and
   says to use §4b for a copy that exists only on `/offsite`.
9. **A slip on the lab, recorded.** While reading Argo CD's version, `oc exec … openshift-gitops-application-controller-0
   -- argocd-application-controller version` started a second controller process in that pod (it logged "ArgoCD
   Application Controller is starting", `v3.4.7+7b6113c`) before the closed pipe ended it. A process listing straight
   after showed PID 1 alone. Nothing it did was observed; the version came from that line.
10. **The review of `8ef0c17e` (OB2, in Codex's seat), decided by the orchestrator on 2026-10-02: approved, both
    findings accepted.** OB2 walked §4d on the lab twice, up to the restore and not including it; each walk returned
    the lab to the chart's render (0 of 163 template fields, the Application spec byte-equal, PVC UIDs unchanged).
    - **F1 (measured), accepted:** step 5's `oc rollout status`, run before Argo CD's apply, reports the recovery
      rollout, which never completed; after the Deployment's ten-minute progress deadline it fails at once
      (`exceeded its progress deadline`). Step 5 now waits for the Application to read Synced first (block 12), and
      T533-6 holds the order (block 17).
    - **F2 (from Argo CD's source), accepted:** the pause does not stop an operation already Running
      (`processRequestedAppOperation` never reads the policy); its retries re-apply Git's render over the hand edit.
      Step 2 prints `{.status.operationState.phase}` beside `enabled`, requires "not `Running`", and terminates a
      running operation first (blocks 12, 17).
    - Note 1's citation of the values-file rule corrected to SPEC_E2's notes and the test that holds it.
    - Remarks, not changed: §4d step 3's `helm pull --untar` is not re-runnable as a block (the text already says to
      re-run only the patch); `/api/version` can read `"leader":false` for a few seconds after the give-back.

## 1. The mandate, and what is out of scope

From #533 ("The change", "Definition of Done") and the orchestrator's mandate:

1. §4a's fallback: `oc debug … -c dashboard -- sh -c '…'` never returns because the oauth-proxy sidecar is copied and
   keeps running. Research `oc debug --one-container` and measure it on the lab.
2. §4c: "the numbers must equal the copy's" fails once the app polls; compare rows up to the copy's highest id.
3. §0: print the command that reads `gsd_build_info` and `gsd_volume_disk_*`.
4. SPEC_E7 §5 step 6's "the database is unchanged by it" is wrong (F4): correct the sentence; SPEC_E7 stays `merged`.
5. #532's known limitation, where an operator reads it (§4 step 5), and the CHANGELOG `## Unreleased` entry 3.0.0
   will carry.
6. The amendments (Orchestrator's notes, 1): the break glass (pause Argo CD, recovery mode by hand, restore, give back
   to Git or roll back with Argo CD), measured on the lab for a plain Application, the ApplicationSet case from the
   documentation; and a Risks box at the top of §4: Argo CD left on during a hand edit, and the endless retry.
7. A test per correction that fails before and passes after.

**Out of scope:** #532's fix (Orchestrator's notes, 4); F1's cause beyond what the runbook must say; F5
(`argocd-wait.sh` and empty `parameters`, a lab tool); a chart change making recovery mode an environment switch
(note 2's open question); §4b and §5 of the runbook. No application, chart, RBAC or ServiceAccount change.

## 2. Research, measured

Web sources were fetched on 2026-10-02 with `curl` and read as text; line numbers are from `curl -s <raw> | nl -ba`.

### 2.1 `oc debug`: what `--one-container` does, and why the command did not return

**Source.** `oc debug --help`, client 4.22.13: "`--one-container=false`: If true, run only the selected container,
remove all others". openshift/oc, branch `release-4.22`,
<https://raw.githubusercontent.com/openshift/oc/release-4.22/pkg/cli/debug/debug.go>:

- L302–304: with a command, "`o.Attach.TTY = false`" and "`o.Attach.Stdin = false`".
- L641–664: without stdin, `oc debug` prints the logs, then "`watchtools.UntilWithSync(ctx, lw, &corev1.Pod{}, preconditionFunc, conditions.PodDone)`",
  and returns `ErrNonZeroExitCode` when the selected container "`State.Terminated.ExitCode != 0`".
- L873–876: "`case o.OneContainer: pod.Spec.InitContainers = nil; pod.Spec.Containers = []corev1.Container{*container}`".
- L518–541: the pod is deleted when the command ends or is interrupted ("Removing debug pod ...").

**Settles.** `oc debug` with a command waits for the whole pod to be done. The Deployment's template has two
containers (`dashboard`, `oauth-proxy`, measured on the lab), the sidecar never exits, so the pod is never done: the
walk's `1/2 NotReady` after 5 min 13 s (F2). With `--one-container` the pod holds the selected container only, and it
is done when the body ends; a failing body (`set -e`) makes the command fail.

### 2.2 `oc debug --one-container` on the lab

The mandated harmless run, at 12:57:37Z against `deploy/group-sync-dashboard` (data claim mounted, only listed):

    $ oc debug -n $NS deploy/$REL --one-container -c dashboard -- sh -c "ls -ln /data >/dev/null; echo done"
    Starting pod/group-sync-dashboard-debug-77q6k, command was: python3.14 -m uvicorn gsd.api:create_app --factory --host 127.0.0.1 --port 8080 --workers 1
    done

    Removing debug pod ...
    exit=0 elapsed=3s
    0                                   # oc get pods | grep -c debug
    group-sync-dashboard-8596b4fb4b-wrdt7   2/2   Running   0     5h55m   # the app: same pod, no restart

**Settles.** It returns, exits 0, in 3 s, and leaves no pod; "command was" names the template's command, which the
`--` command replaces. The non-zero exit of a failing body is from the source (§2.1), not measured.

### 2.3 Row ids: what the app writes after a restore

**Source.** <https://www.sqlite.org/autoinc.html>: "If the AUTOINCREMENT keyword appears after INTEGER PRIMARY KEY,
that changes the automatic ROWID assignment algorithm to prevent the reuse of ROWIDs over the lifetime of the
database." and "The ROWID chosen for the new row is at least one larger than the largest ROWID that has ever before
existed in that same table." This repository: every event table is `id INTEGER PRIMARY KEY AUTOINCREMENT`
(`local-development/gsd/store.py#SCHEMA`: `sync_event`, `membership_event`, `binding_event`, `login_event`).

**The walk.** `walk.log`, steps 5f, 5g and 6e: whole-table counts read `sync_event 2776` and then `2779` against the
copy's `2770`; counted `WHERE id <= ` the copy's `MAX(id)`, all four tables equalled the copy (`membership_event 1843`,
`sync_event 2770`, `binding_event 4328`, `login_event 7968`).

**Settles.** Rows the app writes after the restore take ids above every id the copy holds (the copy carries its
`sqlite_sequence`), so the count up to the copy's highest id is the copy's rows. It falls below the copy's count only
if rows were deleted: retention (runbook §4c, "Retention after a restore") is the expected cause.

### 2.4 `/metrics` through the pod's loopback

**Source.** `gsd_build_info` is defined in `local-development/gsd/metrics.py#DashboardCollector._gather`; the two
gauges in `local-development/gsd/kpi/definitions.py`. The walk read them with `curl -s http://127.0.0.1:8080/metrics`
in the pod (F6, `walk.log` steps 2 and 4). Measured again at 12:57:47Z with the command §0 now prints:

    $ oc exec -n $NS deploy/$REL -c dashboard -- curl -s http://127.0.0.1:8080/metrics | grep -E '^gsd_(build_info|volume_disk_(total|used)_bytes)\{'
    gsd_build_info{branch="main",commit="521c2bb0b4",version="2.4.0"} 1.0
    gsd_volume_disk_used_bytes{component="dashboard"} 1.34537723904e+11
    gsd_volume_disk_total_bytes{component="dashboard"} 1.60456224768e+11
    [exit 0 0]

**Settles.** One read-only command prints step 1's version and step 3's gauges; `grep` runs on the workstation, as
the runbook says of `grep` and `tail` ("What a successful backup looks like").

### 2.5 Argo CD: pausing automated sync, and an ApplicationSet

**Source.** Argo CD v3.4.7 (the lab's controller: `version":"v3.4.7+7b6113c"`),
<https://raw.githubusercontent.com/argoproj/argo-cd/v3.4.7/docs/user-guide/auto_sync.md>:

- L21: "Application CRD now also support explicitly setting automated sync to be turned on or off by using
  `spec.syncPolicy.automated.enabled` flag to true or false. … when set to false controller will skip automated sync
  even if `prune`, `self-heal` and `allowEmpty` are set."
- L34: "For an ApplicationSet managed application, changing the application's `spec.syncPolicy.automated` field will,
  however, have no effect."
- L78: "By default, changes that are made to the live cluster will not trigger automated sync." (L85–91: `selfHeal: true`
  turns that on.)
- L118–120: "Automated sync will only attempt one synchronization per unique combination of commit SHA1 and
  application parameters. If the most recent successful sync in the history was already performed against the same
  commit-SHA and parameters, a second sync will not be attempted, unless `selfHeal` flag is set to true."
- L126: "Rollback cannot be performed against an application with automated sync enabled."

`pkg/apis/application/v1alpha1/types.go` L1499–1504: `IsAutomatedSyncEnabled` is true when "`p.Automated != nil &&
(p.Automated.Enabled == nil || *p.Automated.Enabled)`"; `controller/appcontroller.go` L2237–2239: automated sync
returns early when it is not enabled. `docs/operator-manual/applicationset/Controlling-Resource-Modification.md`
L125–139, "Allow temporarily toggling auto-sync": "you may want to temporarily disable auto-sync for a specific
Application. You can do this by adding an ignore rule for the `spec.syncPolicy.automated` field", with the example
`ignoreApplicationDifferences: - jsonPointers: - /spec/syncPolicy`; L21–35: the `applicationsSync: create-only`
policy "Prevents ApplicationSet controller from modifying or deleting Applications".

**Settles.** `automated.enabled: false` pauses automated sync and self-heal and keeps `prune` and `selfHeal` for the
give-back; removing the field is the undo. On an Application an ApplicationSet generates, the pause holds only if
that ApplicationSet ignores `/spec/syncPolicy` (or does not update Applications); not measured, the lab has none.

### 2.6 Argo CD: the retry, its limit, and ending an operation

**Source.** Argo CD v3.4.7:

- `docs/operator-manual/application.yaml` L254: "`limit: 5 # number of failed sync attempt retries; unlimited number
  of attempts if less than 0`"; L229: "automated sync by default retries failed attempts 5 times".
- `controller/appcontroller.go` L2288–2292: an automated operation gets "`Retry: appv1.RetryStrategy{Limit: 5}`",
  replaced by `app.Spec.SyncPolicy.Retry` when it is set; L1579: a failed operation is retried "`if !terminating &&
  (state.RetryCount < state.Operation.Retry.Limit || state.Operation.Retry.Limit < 0)`"; L1507–1538: a retry of the
  operation in progress, which reads no sync policy; L2241–2243: "Skipping auto-sync: another operation is in
  progress".
- `pkg/apis/application/v1alpha1/types.go` L1513: "Limit is the maximum number of attempts for retrying a failed
  sync. If set to 0, no retries will be performed."; L1517: "Refresh indicates if the latest revision should be used
  on retry instead of the initial one (default: false)".
- `docs/user-guide/commands/argocd_app_terminate-op.md` L5: "Terminate running operation of an application";
  `server/application/application.go` L2459–2468: it sets "`a.Status.OperationState.Phase = common.OperationTerminating`";
  `controller/appcontroller.go` L1570–1576 picks that up, and L1579 retries no terminating operation.
- `server/application/application.go` L2221–2222: rollback is refused, "rollback cannot be initiated when auto-sync
  is enabled"; `docs/user-guide/commands/argocd_app_rollback.md` L5: "Rollback application to a previous deployed
  version by History ID".
- gitops-engine in v3.4.7, `gitops-engine/pkg/health/health_deployment.go` L39–43: a `Progressing` condition with
  reason `ProgressDeadlineExceeded` is `Degraded`; Kubernetes,
  <https://raw.githubusercontent.com/kubernetes/website/main/content/en/docs/concepts/workloads/controllers/deployment.md>
  L1326–1330: `.spec.progressDeadlineSeconds` "defaults to 600". The chart sets none (`grep progressDeadline
  charts/group-sync-dashboard/templates/`: nothing; the lab's Deployment reads `progressDeadlineSeconds=600`).

**The walk (F1).** The recovery-on sync started 05:33:46Z, turned `Degraded` at 05:44:05Z (the 600 s deadline), retried
three times ("Retrying attempt #1 at 5:44AM", "#2 at 5:46AM", "#3 at 5:49AM"), and the recovery-off change applied
at 05:38:43Z started syncing at 05:51:32Z: 12 min 49 s.

**Settles.** A recovery-on sync waits for health it never reaches, fails at the progress deadline, and is retried up to
`limit` times; a negative `limit` never stops, no `retry` block means 5. While it runs, no automated sync starts, so
the next change waits. Pausing automated sync does not stop it (the retry reads no policy); terminating it does.

### 2.7 Server-side apply and hand edits

**Source.** Kubernetes,
<https://raw.githubusercontent.com/kubernetes/website/main/content/en/docs/reference/using-api/server-side-apply.md>
L75–79: "If you remove a field from a manifest and apply that manifest, Server-Side Apply checks if there are any other
field managers that also own the field. If the field is not owned by any other field managers, it is either deleted
from the live object or reset to its default value, if it has one. The same rule applies to associative list or map
items." And for client-side apply,
<https://raw.githubusercontent.com/kubernetes/website/main/content/en/docs/tasks/manage-kubernetes-objects/declarative-config.md>
L509–510: "Calculate the fields to delete. These are the fields present in `last-applied-configuration` and missing
from the configuration file."

**Settles.** Argo CD (with `ServerSideApply=true`, the lab's) re-applies what it renders: a field it owns and a hand
edit changed is set back; a field only the hand edit added has another owner and stays. Measured in §2.10.

### 2.8 Strategic merge patch

**Source.** <https://raw.githubusercontent.com/kubernetes/community/master/contributors/devel/sig-api-machinery/strategic-merge-patch.md>
L125–135: "To delete an element of a list that should be merged:" with `- $patch: delete` and the merge key. Container
`env` and `volumes` merge by `name`, `volumeMounts` by `mountPath`; a `null` value deletes a field.

**Settles.** One strategic patch adds the recovery fields and one removes exactly them (§2.10, phases 4 and 6).

### 2.9 The chart's recovery script, from the chart the release runs

    $ oc get deploy -n group-sync-dashboard group-sync-dashboard -o jsonpath='{.metadata.labels.helm\.sh/chart}'
    group-sync-dashboard-0.61.2
    $ helm pull group-sync-dashboard --repo https://ephico2real2.github.io/group-sync-dashboard --version 0.61.2 --untar --untardir ./break-glass
    $ diff ./break-glass/group-sync-dashboard/scripts/recovery_mode.py charts/group-sync-dashboard/scripts/recovery_mode.py && echo IDENTICAL
    IDENTICAL

`helm template group-sync-dashboard charts/group-sync-dashboard --set recovery.enabled=true` renders the dashboard
container with command `['python3.14', '/scripts/recovery_mode.py', '--release', 'group-sync-dashboard']`, the volume
`{'name': 'recovery-script', 'configMap': {'name': 'group-sync-dashboard-recovery', 'defaultMode': 292}}`, the mount
`{'name': 'recovery-script', 'mountPath': '/scripts', 'readOnly': True}`, `GSD_RECOVERY_MODE=true`,
`GSD_RECOVERY_MODE_TTL=2h`, and no liveness probe: §4d's patch, field for field.

### 2.10 The break glass on the lab, 13:05Z–13:17Z

Logged command by command; the lab's Application `group-sync-dashboard` (namespace `openshift-gitops`) had
`{"automated":{"prune":true,"selfHeal":true},"retry":{"backoff":{"duration":"30s","factor":2,"maxDuration":"5m"},"limit":3},"syncOptions":["CreateNamespace=true","RespectIgnoreDifferences=true","ServerSideApply=true"]}`,
no `ownerReferences`, Synced/Healthy on `main` `521c2bb0`; the Deployment's field managers were `argocd-controller`
(Apply) and `kube-controller-manager`; the pod template was saved.

| Phase | What was done | What was measured |
|---|---|---|
| 1 | Argo CD on. `oc set env … -c dashboard GSD_E10_PROBE=1` at 13:05:47Z | still in the Deployment 4 min 38 s later (13:10:25Z), the Application Synced/Healthy with no new operation: an added field is not put back |
| 1b | `GSD_E10_PROBE-`; then `imagePullPolicy` changed by hand, `Always` → `IfNotPresent`, at 13:10:26Z | back to `Always` 0.7 s later; an automated operation started 13:10:26Z: a field Argo CD renders is put back |
| 2 | `oc patch application.argoproj.io/… --type merge -p '{"spec":{"syncPolicy":{"automated":{"enabled":false}}}}'` at 13:10:43Z | `{"enabled":false,"prune":true,"selfHeal":true}` |
| 3 | `oc set env … GSD_RECOVERY_MODE=true GSD_RECOVERY_MODE_TTL=2h` at 13:10:45Z | pod `2/2 Running`, both variables still set 60 s later; `restore-db.sh --list`: `refused: uvicorn is running here (pid 1): the dashboard may be writing the database`, exit 2 |
| 4 | §4d step 3: the ConfigMap from the chart's script and the strategic patch, at 13:13:01Z | one pod `1/2 Running` at 13:13:05Z; log `RECOVERY MODE (GSD_RECOVERY_MODE=true, GSD_RECOVERY_MODE_TTL=2h)`, `the app is NOT running and no data is collected`, `TTL 2h: ends 2026-10-02T15:13:05Z`; no liveness probe; `restore-db.sh --list`: `pod … · recovery mode, at least 1h59m56s of its TTL left`, four candidates, exit 0. 120 s later the command was still the recovery script and the Application read OutOfSync with no new operation: the pause held |
| 5 | `oc patch … --type json -p '[{"op":"remove","path":"/spec/syncPolicy/automated/enabled"}]'` at 13:15:39Z | the command back to uvicorn 2.6 s later; rollout done 19.8 s after; Synced/Healthy, an automated operation at 13:15:40Z; the policy exactly as before; 10 fields of the pod template differ from the saved one: `GSD_RECOVERY_MODE`, `GSD_RECOVERY_MODE_TTL`, the `/scripts` mount, the `recovery-script` volume; managers `kubectl-set` and `kubectl-patch` still listed |
| 6 | §4d step 6: the removal patch, `oc rollout status`, `oc delete configmap`, 13:16:49Z–13:17:08Z | 0 of 163 fields differ from the saved template; pod-template-hash `8596b4fb4b`, the pre-walk one; managers `argocd-controller` and `kube-controller-manager` only; the ConfigMap `NotFound`; `/api/version` `{"leader":true,"version":"2.4.0",…}`; Synced/Healthy on `521c2bb0` |

PVC UIDs before (13:05:31Z) and after (13:17Z): `group-sync-dashboard-data` `f065b7a4-535c-4ef1-868c-58f5afee4953`,
`group-sync-dashboard-report-artifacts` `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`, `group-sync-dashboard-backup-offsite`
`7f505595-db2e-40be-a4ee-c6ed271c42b6`, unchanged.

**Lab writes.** The Application's `spec.syncPolicy.automated.enabled`, set and removed; the Deployment's pod template,
nine times (phases 1–6), each a `Recreate` rollout of the app; the ConfigMap `group-sync-dashboard-recovery`, created
and deleted; one debug pod (§2.2), removed by `oc debug`. Each start of the app took a scheduled backup (`--list`
showed three new ones, 13:04:18Z to 13:10:58Z), so `keep: 4` rotated three older on-volume copies out. No restore ran,
no PVC was touched, `gsd-cluster-shared-qa` and the fleet account were not used. And note 9's process.

## 2a. Alternatives considered

| Change | Option | Source | Cost here | Decision |
|---|---|---|---|---|
| §4a | `oc debug --one-container` | §2.1, §2.2 | one flag | **Chosen**: returns, exit 0, pod removed (measured) |
| §4a | Ctrl-C after the body, as the walk did | F2 | exit 1 whether or not the body succeeded | Rejected: no success signal |
| §4a | §4b's helper pod for the on-volume copy too | runbook §4b | a YAML file, `oc apply`, `oc delete` | Rejected: three steps where one flag suffices |
| §4c | the copy's highest ids, printed by §1, as arguments | §2.3 | three numbers typed | **Chosen**: works for any copy, on the volume, on `/offsite` or downloaded from S3 |
| §4c | the copy's path in the pod (the walk's 5g) | `walk.log` 5g | none for an on-volume copy | Rejected: after recovery mode the app's pod does not mount `/offsite`, and an S3 copy is not in the pod |
| §4c | whole counts with a tolerance | — | no bound on how much the app writes | Rejected |
| §0 | `curl` through the pod's loopback | §2.4 | none; §4c already uses `curl` there | **Chosen** |
| §0 | `python3.14 -c 'urllib…'` (the runbook's backup-picture form) | runbook | a longer line | Rejected for §0; the other line stays |
| pause | `spec.syncPolicy.automated.enabled: false` | §2.5 | one field set, one removed | **Chosen**: keeps `prune` and `selfHeal` for the give-back; the undo restores the spec exactly (measured) |
| pause | remove `spec.syncPolicy.automated` (the CLI's `--sync-policy none`) | §2.5 | the block must be written back by hand | Rejected |
| pause | an AppProject `deny` sync window | Argo CD `sync_windows.md` L31–40 | stops every Application in the project; needs AppProject rights | Rejected |
| pause | `ignoreApplicationDifferences` on the ApplicationSet | §2.5 | an ApplicationSet change its owners make | **Required** where an ApplicationSet owns the Application; the runbook says to ask (not measured) |
| recovery edit | `oc set env` alone | note 2 | none | Rejected: the app keeps running, `restore-db.sh` refuses (measured) |
| recovery edit | the chart's script in a ConfigMap and one strategic patch | §2.8, §2.9 | a `helm pull`, two commands | **Chosen**: the chart's render field for field (T533-7), measured |
| recovery edit | `helm template --set recovery.enabled=true` piped to `oc apply` | §2.7 | the release's exact values, inline ones included | Rejected: a client-side apply onto an object without `last-applied-configuration` deletes nothing, so the liveness probe would stay (§2.7; the lab's Deployment carries no such annotation) |
| recovery edit | a chart change: the recovery script always shipped, the switch an environment variable | — | chart and image | Out of scope; note 2's open question |
| give-back | end the pause, then remove the added fields | §2.7, §2.10 | one more rollout (19 s) | **Chosen**: back to the chart's render exactly (measured) |
| give-back | `oc replace` with the saved Deployment before ending the pause | — | — | Rejected: on a rollback it would start the newer image on the restored older database, which migrates it again |
| give-back | Argo CD's rollback while paused | §2.6 | refused while automated sync is on | **Documented** as the operator's alternative; Git must say the same before the pause ends |
| endless retry | terminate the running operation | §2.6 | an Argo CD UI or CLI action | **Documented** as the incident step (not measured) |
| endless retry | `retry.refresh: true`, a small `limit` | §2.6 | an Application setting | Left to #532 (note 4) |
| two-digit id | `[A-Z]\d+[a-z]?` | note 5 | one character in two patterns | **Chosen** |

**Reconciliation, research to this repository's code.** `oc debug` waits for `PodDone` (debug.go L645): the
Deployment renders the sidecar beside the app whenever `oauthProxy.enabled`
(`charts/group-sync-dashboard/templates/deployment.yaml#oauth-proxy`), on by default and on the lab, so the plain
command cannot return there. AUTOINCREMENT ids never reuse (sqlite.org): every event table is declared with it
(`local-development/gsd/store.py#SCHEMA`). The two gauges and `gsd_build_info` are what `/metrics` serves
(`local-development/gsd/metrics.py#DashboardCollector._gather`). `restore-db.sh` refuses without
`GSD_RECOVERY_MODE=true` in the pod spec (`local-development/restore-db.py#preflight`) and with uvicorn running
(`local-development/restore-db.py#in_recovery`), which is why the edit needs the command as well as the variables.
The recovery script is the chart's, mounted from a ConfigMap the chart renders only in recovery mode
(`charts/group-sync-dashboard/templates/recovery.yaml#Rendered only while recovery.enabled is true`); the patch
creates the same names. The chart refuses `RollingUpdate` at one replica with persistence
(`charts/group-sync-dashboard/templates/deployment.yaml#strategy=RollingUpdate is unsafe at replicaCount 1`), so the
edit's rollout stops the app before the recovery pod starts. A Deployment's progress deadline makes Argo CD read it
`Degraded` (gitops-engine L39–43): the recovery render's readiness probe cannot pass
(`charts/group-sync-dashboard/templates/deployment.yaml#a readiness probe that cannot pass`), so every recovery-on sync
ends that way and is retried. `prepare-release.py` matches index ids with one pattern
(`local-development/prepare-release.py#_INDEX_MERGED`), the index test with another
(`local-development/tests/test_specs_index.py#INDEX_ROW`): both read one digit today.

## 3. The design

### 3.1 §4a: the helper pod runs the dashboard container alone

`oc debug -n $NS deploy/$REL --one-container -c dashboard -- sh -c '…'`, in the command and in the sentence that
tells recovery mode's `oc exec` to replace it. The paragraph says why: without the flag the copied sidecar never ends
and `oc debug` does not return. The body is unchanged.

### 3.2 §4c: counted up to the copy's highest id

§1's snippet prints, per table, `<table> <rows> rows, highest id <id>` (`COALESCE(MAX(id), 0)`, so an empty table
prints 0). §4c's snippet takes the three highest ids as arguments, refuses a different number of arguments, and prints
`<table> <rows> rows up to id <id>`. Each must equal §1's rows. The text says why a whole count grows (the walk's
numbers) and the one expected reason for a lower count (retention). The snippet opens the live file `mode=ro`, as
before.

### 3.3 §0: the `/metrics` read

One command in step 1, through the pod's loopback, filtered on the workstation to the three series; step 3's sentence
refers to it instead of saying "Without `oc`".

### 3.4 §4: the Risks box and step 5

After the "In order" paragraph, which gains one sentence naming §4d as the one exception to the values-file rule, a
blockquote **Risks under Argo CD** states both risks with the lab's numbers, before step 1. Step 5 no longer says the
recovery pod stops "at once": where the GitOps controller retries a failed sync the change waits, 12 min 49 s on the
lab, a known limitation of this release tracked in #532. Step 5 does not name Argo CD: steps 1 to 5 are the values-file
path, and `local-development/tests/test_chart_recovery_mode.py#test_the_only_documented_path_is_the_values_file` (SPEC_E2's
rule) lets a sentence there name it only for what it reverts; the box above names it.

### 3.5 §4d: the break glass

Seven steps, each a command block that was walked except where it says otherwise:

1. Find the Application from the Deployment's `argocd.argoproj.io/tracking-id` annotation and read its
   `ownerReferences`; an ApplicationSet owner means the pause holds only with `ignoreApplicationDifferences` on
   `/spec/syncPolicy`.
2. Pause (`automated.enabled: false`) and confirm `false` with no operation `Running`, again a minute later, before
   anything else; a running operation is terminated first (step 7's command), because its retries re-apply Git's render.
3. The recovery edit: the chart version from the `helm.sh/chart` label, the script from `helm pull` of that version,
   the ConfigMap `$REL-recovery`, one strategic patch. Why the variables alone do not do it, measured. Release at one
   replica (recovery mode and `restore-db.sh` need one pod).
4. `restore-db.sh --list`, then `--from-version <ID>`, as **The script, in recovery mode** says.
5. Give back: a rollback commits its `image.tag` to Git first; remove `automated.enabled`; wait for Synced (before it,
   `oc rollout status` reports the recovery rollout, which fails at once after the progress deadline, measured); `oc rollout status`. With
   `selfHeal` off and Git unchanged, sync once by hand (documented, not measured). Argo CD's rollback while paused is
   the operator's alternative, with Git made to agree before the pause ends.
6. Remove what the edit added (the removal patch, the rollout, the ConfigMap), then §4c.
7. The endless retry, an incident step: pause, then terminate the running operation (UI or `argocd app terminate-op
   $APP`); restore; commit `recovery.enabled: false`; end the pause. Not measured.

### 3.6 The budgets

- **One writer on `gsd.db`, over the break glass, for this release.** From step 3's rollout until step 5's, no uvicorn
  runs: `Recreate` stops the app before the recovery pod starts, the recovery script never opens the database
  (`charts/group-sync-dashboard/scripts/recovery_mode.py`), and `restore-db.sh` refuses while uvicorn runs. The only
  thing that could start the app early is Argo CD, which is paused, confirmed before step 3. Holds for one
  Application; with an ApplicationSet that does not ignore `/spec/syncPolicy` it does not hold, and step 1 stops there.
- **What the break glass writes.** One field of one Application (set, then removed); one ConfigMap (created, then
  deleted); the Deployment's pod template, twice by hand and once by Argo CD; three rollouts. Nothing else, on no other
  Application, and no permission is granted or removed.
- **How long the app is down.** From step 3's rollout to step 5's (the lab's: 4 s to the recovery pod, 19.8 s for the
  give-back's rollout), plus step 6's restart (19 s on the lab).
- **The values-file path under a retry policy.** Turning recovery off waits at most until the recovery-on operation
  has run out of retries: `progressDeadlineSeconds` (600 s) plus each retry and its backoff; unbounded with a negative
  `limit`. 12 min 49 s measured with `limit: 3`.

### 3.7 What does not change

The values-file path stays the planned path; no chart, image, RBAC or ServiceAccount change; the restore script and
its refusals; §4b and §5; SPEC_E7's status (`merged`).

## 4. Tests

### 4.1 One test per change

| Test | File | Holds | Fails without the change because |
|---|---|---|---|
| T533-1 | `test_runbook_backup_restore.py` | every `oc debug` the runbook prints carries `--one-container` | §4a prints it twice without the flag |
| T533-2 | same | §1 prints each table's highest id and §4c counts up to it: both snippets run as printed, on a copy and on a live file with rows added after it | §1 prints `membership_event 5`, no highest id |
| T533-3 | same | §0 prints one `/metrics` read whose filter keeps exactly the three measured series | §0 prints no such command |
| T533-4 | same | SPEC_E7 §5 step 6 says the fallback's restore sets the database back to the copy | it says "the database is unchanged by it" |
| T533-5 | same | §4's Risks box precedes step 1 and names both risks with the lab's numbers; step 5 names the delay and #532 | no box; step 5 says "stops at once" |
| T533-6 | same | §4d is §4's last subsection and prints its commands in order: find, ApplicationSet, pause, confirm, ConfigMap, patch, restore, unpause, removal, ConfigMap deleted, terminate | no §4d |
| T533-7 | same (needs `helm`) | the hand patch equals the chart's `recovery.enabled: true` render (command, variables, mount, volume, no liveness probe), and the removal patch deletes exactly what it added | no §4d |
| T533-8 | `test_prepare_release.py` | a two-digit id's `merged` row and header become `released` | the release is refused: the header is merged and the row is not read |
| T300-10 (changed) | `test_runbook_backup_restore.py` | the values-file prohibitions and the Argo CD sentence rule hold for §4 outside the Risks box and §4d | — (it passes before; after the change it would fail without its exemption) |
| the undo test (changed) | `test_restore_db.py` | runs §4a's body, found by its new first line, and the old database comes back whole | it finds no line with `--one-container` before the change (`StopIteration`) |

### 4.2 The commands

    cd <tree>/local-development
    PYTHONPATH=<tree>/local-development .venv/bin/python -m pytest -q tests/test_runbook_backup_restore.py tests/test_prepare_release.py

### 4.3 Before and after, measured

Recorded on a throwaway worktree of `521c2bb0` (§7 applied with `--apply`, the three changed test files kept,
everything else put back to `521c2bb0`; then the whole of §7 applied), with
`PYTHONPATH=<tree>/local-development`:

    $ python3 local-development/apply-spec-blocks.py docs/specs/SPEC_E10_runbook_corrections.md <tree>
    21 blocks check out across 7 files

    before: pytest tests/test_runbook_backup_restore.py tests/test_prepare_release.py tests/test_restore_db.py tests/test_chart_recovery_mode.py
    FAILED test_t533_1  ['oc debug -n $NS deploy/$REL -c dashboard --', "oc debug -n $NS deploy/$REL -c dashboard -- sh -c '"]
    FAILED test_t533_2  §1 prints no row count and highest id for membership_event: '…membership_event 5\nsync_event 7\nlogin_event 3\n'
    FAILED test_t533_3  assert 0 == 1 (no /metrics read in §0)
    FAILED test_t533_4  'the database is unchanged by it' is contained here
    FAILED test_t533_5  '> **Risks under Argo CD**' not in §4
    FAILED test_t533_6  ['4a', '4b', '4c'] == ['4a', '4b', '4c', '4d']
    FAILED test_t533_7  IndexError (no §4d)
    FAILED test_a_release_promotes_merged_status_cells (T533-8)  ERROR: header Status is merged but the index is not: ['SPEC_Z10_example.md']
    FAILED test_the_runbooks_undo_leaves_the_old_database_whole_when_gsd_db_cannot_be_written  StopIteration
    9 failed, 132 passed in 25.39s

    after: the same four files, tests/test_specs_index.py and tests/test_docs_citations.py
    1971 passed, 19 skipped in 42.16s

    after: the whole suite, pytest -q tests/
    7459 passed, 27 skipped, 5 xfailed, 2 warnings in 588.75s (0:09:48)

    $ markdownlint-cli2 docs/RUNBOOK_backup_restore.md
    Summary: 6 issues in 1 file          # before and after: the same six (MD004 at the pictures' list, MD040 x3), none new

    $ BASE=521c2bb0 python3 local-development/check-app-version-bump.py      # on a commit of the applied tree
    no image content changed (publish.yml paths, excluding version fields); no bump needed

Lines added and removed (`git diff --numstat 521c2bb0`): `docs/CHANGELOG.md` +16 −0, `docs/RUNBOOK_backup_restore.md`
+161 −18, `docs/specs/SPEC_E7_schema_line_and_runbook.md` +3 −1, `local-development/prepare-release.py` +2 −1,
`local-development/tests/test_prepare_release.py` +8 −1, `local-development/tests/test_restore_db.py` +2 −1,
`local-development/tests/test_runbook_backup_restore.py` +190 −2. In this spec's own commit:
`local-development/tests/test_specs_index.py` (the two-digit id, the count 49, E10 pinned to #533 and excluded by id) and
the index row; with E10's issue mistyped as #535 in row and header, `test_issue_numbers_are_unique_and_follow_the_implementation_order`
fails `('E10 is #533', '535')`, and with the pattern back to one digit the count fails "expected forty-nine index rows".

## 5. On the lab

Measured now, read-only or as recorded in §2.2 and §2.10: the `oc debug --one-container` run, the `/metrics` read, the
break glass from step 1 to `restore-db.sh --list` and steps 5 and 6, the lab put back. The implementing pull request
walks each correction as the merged runbook prints it, with `release-crc.sh` (development), the output saved as text
under `reports/<date>_runbook-corrections-533/`:

1. **Before.** The three PVC UIDs (§2.10's), the Application's `spec.syncPolicy`, the Deployment's pod template saved.
2. **§0.** The `/metrics` read: three lines.
3. **§1 and §4, the scripted path.** §1 on the newest backup (with its highest ids), recovery on through the values
   file, `restore-db.sh --from-version` of that backup, recovery off: the Risks box's delay seen again (the Application's
   operation retrying, the off change waiting), then §4c's count with §1's ids: each equal.
4. **§4a, the fallback.** `replicaCount: 0`, §4a's `oc debug --one-container` body with the same copy: it returns, exit
   0, no pod left; `replicaCount: 1`; §4c.
5. **§4d, the break glass, with a restore.** Steps 1 to 6 as printed, `--from-version` of the newest backup in step 4;
   after step 6 the pod template equals the saved one (0 differences) and §4c's counts equal §1's.
6. **After.** The PVC UIDs, unchanged; the Application on `main`, Synced/Healthy, its `spec.syncPolicy` as in step 1.

Step 7 of §4d (terminate a retrying operation) is walked only if the operator agrees to it on the lab.

## 6. What an operator sees, and what it costs

- **Before an upgrade (§0):** one more command, three lines of output.
- **Restoring by hand (§4a):** the helper command returns when the body ends, with its exit status.
- **Verifying (§4c):** three numbers from §1 typed into the count; each line equal to §1's, however long the app has run.
- **Under Argo CD:** §4 opens with the two risks. In an incident, §4d: about ten commands, the app down from the edit
  to the give-back, one extra restart at the end; rights to patch the release's Application are needed. On the planned
  path, turning recovery off can wait up to the retries' end (12 min 49 s on the lab).
- **Release engineering:** `prepare-release.py` reads E10's row; nothing else changes. No GUI, chart, RBAC or image
  change.

## 7. Implementation blocks

Twenty-one blocks, in order: the runbook (1–12), SPEC_E7 (13), the CHANGELOG (14), the runbook's tests (15–17),
`prepare-release.py` and its test (18–20), and the restore test that runs §4a's body (21). New runbook code blocks use four backticks
(`local-development/apply-spec-blocks.py#FENCE` ends a block's fence at the first line of exactly three; SPEC_E7's
Orchestrator's notes, 6).

### Block 1 — docs/RUNBOOK_backup_restore.md: §0 step 1 prints the `/metrics` read

T533-3 (§3.3).

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
   (`local-development/prepare-release.py#SCHEMA_LINE`); an epic's GitHub release lists its children's lines. The
   schema you leave is the one the running image understands, read without opening the live file:
```

New text:

```text
   (`local-development/prepare-release.py#SCHEMA_LINE`); an epic's GitHub release lists its children's lines. The
   version you run, and the two volume gauges step 3 compares, are read from `/metrics` through the pod's loopback,
   where the app listens; nothing is opened or written, and `grep` runs on your workstation:

   ````sh
   oc exec -n $NS deploy/$REL -c dashboard -- curl -s http://127.0.0.1:8080/metrics | grep -E '^gsd_(build_info|volume_disk_(total|used)_bytes)\{'
   ````

   It prints three lines: `gsd_build_info{branch="main",commit="…",version="<the version you run>"} 1.0` and the two
   gauges in bytes. The schema you leave is the one the running image understands, read without opening the live
   file:
```

### Block 2 — docs/RUNBOOK_backup_restore.md: §0 step 3 refers to that read

T533-3 (§3.3).

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
   Without `oc`, `/metrics` carries the volume's numbers: `gsd_volume_disk_total_bytes{component="dashboard"}` minus
   `gsd_volume_disk_used_bytes{component="dashboard"}` is the free space, or more than the copy may use where the
   filesystem keeps blocks for root (`mke2fs` reserves 5% by default).
```

New text:

```text
   Step 1's `/metrics` read printed the volume's numbers too, and Prometheus has them where it scrapes the dashboard:
   `gsd_volume_disk_total_bytes{component="dashboard"}` minus `gsd_volume_disk_used_bytes{component="dashboard"}` is
   the free space, or more than the copy may use where the filesystem keeps blocks for root (`mke2fs` reserves 5% by
   default).
```

### Block 3 — docs/RUNBOOK_backup_restore.md: §1 prints each table's highest id

T533-2 (§3.2).

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
for t in ("membership_event", "sync_event", "login_event"):
    print(t, c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
' /data/backup/gsd-20260904T061500.123456Z.db
```

New text:

```text
for t in ("membership_event", "sync_event", "login_event"):
    n, top = c.execute(f"SELECT COUNT(*), COALESCE(MAX(id), 0) FROM {t}").fetchone()
    print(t, n, "rows, highest id", top)
' /data/backup/gsd-20260904T061500.123456Z.db
```

### Block 4 — docs/RUNBOOK_backup_restore.md: §1 says what the highest ids are for

T533-2 (§3.2).

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
Expected: `integrity_check: ok`, a `user_version` equal to the running app's latest migration,
and row counts that are plausible for the age of the copy.
```

New text:

```text
Expected: `integrity_check: ok`, a `user_version` equal to the running app's latest migration,
and row counts that are plausible for the age of the copy. Keep the three highest ids of the copy you restore: §4c
counts the restored file up to them.
```

### Block 5 — docs/RUNBOOK_backup_restore.md: §4 names its one exception, and the risks under Argo CD

T533-5 (§3.4); the operator's amendments (Orchestrator's notes, 1).

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
release goes through its values file and its deployment pipeline, never `oc scale` or `oc set env`: a GitOps
controller that self-heals, Argo CD's for one, reverts a hand edit to an object it renders.
```

New text:

```text
release goes through its values file and its deployment pipeline, never `oc scale` or `oc set env`: a GitOps
controller that self-heals, Argo CD's for one, reverts a hand edit to an object it renders. The one exception is §4d,
the break glass for an incident on a release Argo CD syncs, which pauses Argo CD's automated sync first, puts the pod
into recovery mode by hand, restores with the same script and gives the release back to Git.

> **Risks under Argo CD** (measured on the CRC lab with Argo CD v3.4.7, 2026-10-02; #533, #532)
>
> * **Argo CD left on during a hand edit.** With `syncPolicy.automated.selfHeal: true`, Argo CD puts back within a
>   second a field it renders that was changed by hand (an `imagePullPolicy` changed by hand was back 0.7 s later),
>   and leaves a field that only the hand edit added (an added variable was still there 4 min 38 s later, the
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
```

### Block 6 — docs/RUNBOOK_backup_restore.md: §4 step 5 states the delay, #532's known limitation

T533-5 (§3.4). The step names no Argo CD: steps 1 to 5 are the values-file path, where
`local-development/tests/test_chart_recovery_mode.py#test_the_only_documented_path_is_the_values_file` lets a sentence
name Argo CD only to say what it reverts (SPEC_E2's rule); the risks box above it names it.

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
   older `image.tag`) and roll it out. When the change is applied the recovery pod stops at once and the app
   starts on the restored file.
```

New text:

```text
   older `image.tag`) and roll it out. When the change is applied the recovery pod stops and the app starts on the
   restored file. Where the release's GitOps controller retries a failed sync (a `syncPolicy.retry` policy), the
   change waits until the retries of the sync that turned recovery on have run out, 12 min 49 s on the lab, and the
   recovery pod keeps running until then (#532, a known limitation of this release, and the risks box above).
```

### Block 7 — docs/RUNBOOK_backup_restore.md: §4a's helper runs the dashboard container alone, and why

T533-1 (§3.1).

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
`oc exec -n $NS deploy/$REL -c dashboard --` in place of `oc debug -n $NS deploy/$REL -c dashboard --`.
Otherwise, a helper pod with the data claim, from the Deployment's own template:
```

New text:

```text
`oc exec -n $NS deploy/$REL -c dashboard --` in place of `oc debug -n $NS deploy/$REL --one-container -c dashboard --`.
Otherwise, a helper pod with the data claim, from the Deployment's own template, with the dashboard container alone:
without `--one-container` the pod also runs the oauth-proxy sidecar, which never exits, and `oc debug` waits for every
container of its pod, so it does not return (the #300 walk waited 5 min 13 s; with the flag the lab's run returned in
3 s, exit 0, its pod removed). A body that fails makes the command fail:
```

### Block 8 — docs/RUNBOOK_backup_restore.md: §4a's command

T533-1 (§3.1).

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
oc debug -n $NS deploy/$REL -c dashboard -- sh -c '
```

New text:

```text
oc debug -n $NS deploy/$REL --one-container -c dashboard -- sh -c '
```

### Block 9 — docs/RUNBOOK_backup_restore.md: §4c counts up to the copy's highest ids

T533-2 (§3.2).

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
Then the counts, on the live file this time (a normal open, the pod's own connection is the writer):
```

New text:

```text
Then the counts, on the live file this time (opened read-only beside the app's own connection), each up to the copy's
highest id in that table, as §1 printed it:
```

### Block 10 — docs/RUNBOOK_backup_restore.md: §4c's count

T533-2 (§3.2).

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
import sqlite3
c = sqlite3.connect("file:/data/gsd.db?mode=ro", uri=True)
for t in ("membership_event", "sync_event"):
    print(t, c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
'
```

New text:

```text
import sqlite3, sys
assert len(sys.argv) == 4, "give the three highest ids of the copy, as §1 printed them"
c = sqlite3.connect("file:/data/gsd.db?mode=ro", uri=True)
for t, top in zip(("membership_event", "sync_event", "login_event"), map(int, sys.argv[1:])):
    print(t, c.execute(f"SELECT COUNT(*) FROM {t} WHERE id <= ?", (top,)).fetchone()[0], "rows up to id", top)
' <membership-highest-id> <sync-highest-id> <login-highest-id>
```

### Block 11 — docs/RUNBOOK_backup_restore.md: §4c says why a whole count does not match

T533-2 (§3.2).

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
The numbers must equal the copy's (§1). The pod log shows `schema migration N applied` lines
```

New text:

```text
Each number must equal the copy's row count in §1. A count of the whole table does not: the leader polls as soon as it
starts, and the rows it writes take ids above every id in the copy (SQLite's `AUTOINCREMENT`), so the #300 walk read
2776 and then 2779 `sync_event` rows against the copy's 2770 while the count up to the copy's highest id stayed 2770.
A count below the copy's means rows the copy had are gone; retention pruning them (**Retention after a restore**,
below) is the one expected reason. The pod log shows `schema migration N applied` lines
```

### Block 12 — docs/RUNBOOK_backup_restore.md: §4d, the break glass under Argo CD

T533-6, T533-7 (§3.5); measured in §2.10.

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
## 5. Moving the data to a new claim (access mode change)
```

New text:

```text
### 4d. Break glass under Argo CD: pause, recovery mode by hand, give back

For an incident on a release Argo CD syncs (#533; the operator's decision of 2026-10-02). It replaces steps 1, 2 and
5 of the values-file path; the restore is the same script. Every step was walked on the CRC lab (Argo CD v3.4.7, chart
0.61.2) except the restore itself, the ApplicationSet case and step 7, which follow Argo CD's documentation. You need
the right to patch the release's Application in Argo CD's namespace, `helm`, and a release at one replica (recovery
mode and `restore-db.sh` need exactly one pod).

1. **Find the Application, and whether an ApplicationSet owns it.** The Deployment's tracking annotation reads
   `<APP>:apps/Deployment:<namespace>/<name>`; Argo CD's namespace is `openshift-gitops` on OpenShift GitOps:

   ````sh
   oc get deploy -n $NS $REL -o jsonpath='{.metadata.annotations.argocd\.argoproj\.io/tracking-id}{"\n"}'
   APP=<the name before the first colon>; ARGO_NS=openshift-gitops
   oc get application.argoproj.io/$APP -n $ARGO_NS -o jsonpath='{.metadata.ownerReferences[*].kind}{"\n"}'
   ````

   `ApplicationSet` in the output means a change to this Application's `spec.syncPolicy` "will, however, have no
   effect" (Argo CD, "Temporarily toggling auto-sync for applications managed by ApplicationSets"): the ApplicationSet
   puts it back unless it lists `/spec/syncPolicy` under `ignoreApplicationDifferences`. That is a change to the
   ApplicationSet, made by its owners; ask them before you go on.
2. **Pause automated sync, and confirm the pause held and no operation is running before you touch anything else:**

   ````sh
   oc patch application.argoproj.io/$APP -n $ARGO_NS --type merge -p '{"spec":{"syncPolicy":{"automated":{"enabled":false}}}}'
   oc get application.argoproj.io/$APP -n $ARGO_NS -o jsonpath='{.spec.syncPolicy.automated.enabled} {.status.operationState.phase}{"\n"}'
   ````

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
   mode, at least 1h59m56s of its TTL left`) and listed its copies:

   ````sh
   local-development/restore-db.sh --list --namespace $NS --release $REL
   local-development/restore-db.sh --from-version <ID> --namespace $NS --release $REL
   ````

5. **Give the release back to Git.** For a rollback, first commit the older `image.tag`, and anything else the
   restored database needs, to the release's values file. Then end the pause, wait until Argo CD has applied, and
   wait for the app:

   ````sh
   oc patch application.argoproj.io/$APP -n $ARGO_NS --type json -p '[{"op":"remove","path":"/spec/syncPolicy/automated/enabled"}]'
   oc wait application.argoproj.io/$APP -n $ARGO_NS --for=jsonpath='{.status.sync.status}'=Synced --timeout=5m
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
   up to its `limit`. **Incident step:** pause (step 2), then terminate the operation, from the Application's sync
   status in the Argo CD UI or with the Argo CD CLI; a terminating operation is not retried:

   ````sh
   argocd app terminate-op $APP
   ````

   The pod stays in the recovery mode the chart rendered, and steps 3 and 6 do not apply. Restore (step 4), commit
   `recovery.enabled: false` to the values file, and end the pause (step 5): with no operation running, automated
   sync takes the new revision. Not measured on the lab.

## 5. Moving the data to a new claim (access mode change)
```

### Block 13 — docs/specs/SPEC_E7_schema_line_and_runbook.md: §5 step 6 says what the fallback's restore does

T533-4. SPEC_E7's status stays `merged`; the sentence was a prediction the walk refuted (F4).

<!-- block: docs/specs/SPEC_E7_schema_line_and_runbook.md | edit -->

Old text:

```text
   `oc debug` body with the copy the walk restored in step 5 (the database is unchanged by it); `replicaCount: 1`,
```

New text:

```text
   `oc debug` body with the copy the walk restored in step 5 (it sets the database back to that copy and discards what
   the app wrote since step 5: the #300 walk's F4 measured `sync_event` 2776 → 2770 and `login_event` 7992 → 7968;
   corrected by SPEC_E10); `replicaCount: 1`,
```

### Block 14 — docs/CHANGELOG.md: the entry 3.0.0 carries

First under `## Unreleased`.

<!-- block: docs/CHANGELOG.md | edit -->

Old text:

```text
## Unreleased

```

New text:

```text
## Unreleased

- **The backup runbook, corrected from the #300 walk, with a break glass under Argo CD; #532 stated as a known
  limitation (#533, Epic E #385, `docs/specs/SPEC_E10_runbook_corrections.md`).** §4a's helper is `oc debug
  --one-container`: without it the debug pod also ran the oauth-proxy sidecar, which never exits, and `oc debug` never
  returned (with it: 3 s, exit 0, its pod removed). §1 prints each table's highest id and §4c counts the restored file
  up to it, because the leader's first polls add rows a whole count cannot match. §0 prints the `/metrics` read for
  `gsd_build_info` and the two volume gauges. §4 opens with the risks under Argo CD, and the new §4d is the break glass
  for an incident on a release Argo CD syncs: pause automated sync and confirm it held, put the pod into recovery mode
  by hand (the chart's recovery script in a ConfigMap and one patch; `GSD_RECOVERY_MODE` alone leaves the app
  running), restore with `restore-db.sh`, give the release back to Git, then remove what the hand edit added, which
  Argo CD leaves in place. **The risks §4 now states, and a known limitation (#532):** with Argo CD left on, self-heal puts back the fields it renders
  within a second (0.7 s measured) and would start the app during a hand-edited restore; and on the values-file path,
  turning recovery mode off under a sync `retry` policy waits until the retries of the sync that turned it on have
  failed, 12 min 49 s on the lab with `limit: 3`, without end with a `limit` below 0; §4d step 7 is the way out.
  SPEC_E7 §5 step 6 now says the fallback's restore sets the database back to the copy, and `prepare-release.py`
  reads a two-digit spec id. No application or chart change.

```

### Block 15 — local-development/tests/test_runbook_backup_restore.py: the docstring and the imports

<!-- block: local-development/tests/test_runbook_backup_restore.py | edit -->

Old text:

```text
(gsd/store.py), a chart refusal cites "§5", and the chart README links "#6-pre-upgrade-copies".
"""

from __future__ import annotations

import pathlib
import re
```

New text:

```text
(gsd/store.py), a chart refusal cites "§5", and the chart README links "#6-pre-upgrade-copies".

#533 corrected four instructions the #300 walk ran as printed, and added §4's risks under Argo CD and the §4d break
glass (docs/specs/SPEC_E10_runbook_corrections.md); their tests are T533-1 to T533-7.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import sqlite3
import subprocess
import sys

import pytest
import yaml
```

### Block 16 — local-development/tests/test_runbook_backup_restore.py: T300-10 exempts the Risks box and §4d

The values-file prohibitions and the Argo CD sentence rule keep holding for every other line of §4 (§3.4, note 1).

<!-- block: local-development/tests/test_runbook_backup_restore.py | edit -->

Old text:

```text
    # the only Helm command line is the one labelled for development and troubleshooting
    operator = re.sub(r"\*\*Development and troubleshooting only:\*\*.*?\n\n", "", body, flags=re.S)
    for word in ("helm upgrade", "--set", "argocd", "applications.argoproj.io", "oc patch", "oc set env deploy"):
        assert word not in operator.lower(), word
    for sentence in re.split(r"(?<=[.;:])\s+", operator):
        assert "Argo CD" not in sentence or "revert" in sentence, sentence
```

New text:

```text
    # the only Helm command line is the one labelled for development and troubleshooting; the break glass (§4d, the
    # last subsection) and the risks box it answers are the one place where Argo CD's controls and hand edits are the
    # path (#533, the operator's decision of 2026-10-02); elsewhere Argo CD is named for what it reverts, §4d or #532
    operator = re.sub(r"\*\*Development and troubleshooting only:\*\*.*?\n\n", "", body, flags=re.S)
    operator = "\n".join(line for line in operator.split("### 4d.", 1)[0].splitlines() if not line.startswith(">"))
    for word in ("helm upgrade", "--set", "argocd", "applications.argoproj.io", "oc patch", "oc set env deploy"):
        assert word not in operator.lower(), word
    for sentence in re.split(r"(?<=[.;:])\s+", operator):
        assert "Argo CD" not in sentence or any(word in sentence for word in ("revert", "§4d", "#532")), sentence
```

### Block 17 — local-development/tests/test_runbook_backup_restore.py: T533-1 to T533-7

<!-- block: local-development/tests/test_runbook_backup_restore.py | edit -->

Old text:

```text
    assert linked <= anchors, f"links to anchors the runbook does not have: {linked - anchors}"
```

New text:

```text
    assert linked <= anchors, f"links to anchors the runbook does not have: {linked - anchors}"


# ── #533: the corrections from the #300 walk, and the break glass under Argo CD (SPEC_E10) ─────────────────────────

def python_body(text: str, first_line: str) -> str:
    """The Python of the first `python3.14 -c '…'` command in `text` whose code starts with `first_line`: from the
    line after the opening quote to the line before the closing one, as the operator's shell passes it."""
    start = text.index(f"-c '\n{first_line}\n") + len("-c '\n")
    return text[start:text.index("\n'", start)] + "\n"


def flat(text: str) -> str:
    """Prose with its line breaks, indentation and blockquote markers folded, so a wrapped phrase still matches."""
    return " ".join(" ".join(re.sub(r"^\s*>\s?", "", line) for line in text.splitlines()).split())


def test_t533_1_oc_debug_runs_the_dashboard_container_alone() -> None:
    """§4a's helper pod is `oc debug` of the Deployment, which copies every container of its template. With the
    oauth-proxy sidecar copied the pod never completes and `oc debug` never returns (the #300 walk, F2); with
    `--one-container` it ran the body, exited 0 in 3 s and removed its pod (SPEC_E10 §2.2). Every `oc debug` command
    the runbook prints carries the flag."""
    uses = re.findall(r"oc debug [^`\n]*", TEXT)
    assert uses, "the runbook prints no oc debug command"
    assert all("--one-container" in use for use in uses), [use for use in uses if "--one-container" not in use]


def test_t533_2_section_4c_counts_up_to_the_copys_highest_id(tmp_path: pathlib.Path) -> None:
    """§4c compared whole-table counts with the copy's, which fails as soon as the leader polls (the #300 walk read
    2776, then 2779 `sync_event` rows against the copy's 2770). §1 now prints each table's highest id and §4c counts
    the live file up to it. Both snippets run here as printed: on a copy, and on a live file holding the copy's rows
    and rows written after the restore, which take higher ids (AUTOINCREMENT)."""
    tables = {"membership_event": 5, "sync_event": 7, "login_event": 3}
    copy, live = tmp_path / "copy.db", tmp_path / "gsd.db"
    c = sqlite3.connect(copy)
    for table, rows in tables.items():
        c.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY AUTOINCREMENT, note TEXT)")
        c.executemany(f"INSERT INTO {table} (note) VALUES (?)", [("copy",)] * rows)
    c.commit()
    c.close()
    shutil.copyfile(copy, live)
    c = sqlite3.connect(live)                       # the leader's first polls after the restore
    c.executemany("INSERT INTO sync_event (note) VALUES (?)", [("after",)] * 6)
    c.executemany("INSERT INTO login_event (note) VALUES (?)", [("after",)] * 2)
    c.commit()
    c.close()
    printed = subprocess.run([sys.executable, "-c", python_body(section("1"), "import sqlite3, sys"), str(copy)],
                             capture_output=True, text=True, check=True).stdout
    tops = []
    for table, rows in tables.items():
        found = re.search(rf"^{table} (\d+) rows, highest id (\d+)$", printed, re.M)
        assert found, f"§1 prints no row count and highest id for {table}: {printed!r}"
        assert int(found[1]) == rows, (table, printed)
        tops.append(found[2])
    count = python_body(section("4").split("### 4c.", 1)[1], "import sqlite3, sys").replace("/data/gsd.db", str(live))
    counted = subprocess.run([sys.executable, "-c", count, *tops], capture_output=True, text=True, check=True).stdout
    for table, rows in tables.items():
        found = re.search(rf"^{table} (\d+) rows up to id (\d+)$", counted, re.M)
        assert found and int(found[1]) == rows, (table, counted)


def test_t533_3_section_0_prints_the_metrics_read() -> None:
    """§0 named `gsd_build_info` and the two `gsd_volume_disk_*` gauges and printed no command to read them (the #300
    walk, F6). It prints one read through the pod's loopback, and its filter keeps exactly the three series the lab
    served (SPEC_E10 §2.4) and nothing else of a scrape."""
    reads = [line for line in code_lines(section("0")) if "curl -s http://127.0.0.1:8080/metrics" in line]
    assert len(reads) == 1, reads
    assert reads[0].startswith("oc exec -n $NS deploy/$REL -c dashboard -- curl -s http://127.0.0.1:8080/metrics | grep -E '")
    pattern = re.compile(reads[0].split("grep -E '", 1)[1].rsplit("'", 1)[0])
    scrape = [
        'gsd_build_info{branch="main",commit="521c2bb0b4",version="2.4.0"} 1.0',
        'gsd_volume_disk_used_bytes{component="dashboard"} 1.34537723904e+11',
        'gsd_volume_disk_total_bytes{component="dashboard"} 1.60456224768e+11',
        "# HELP gsd_build_info Always 1; the running build is carried in the labels.",
        "gsd_backup_last_success_timestamp_seconds 1.7904500667085032e+09",
    ]
    assert [line for line in scrape if pattern.search(line)] == scrape[:3]


def test_t533_4_spec_e7_says_the_fallback_restore_sets_the_database_back() -> None:
    """SPEC_E7 §5 step 6 said §4a's restore of the copy step 5 restored leaves "the database … unchanged". The app had
    written rows in between, and the restore discarded them (the #300 walk, F4)."""
    spec = (REPO / "docs" / "specs" / "SPEC_E7_schema_line_and_runbook.md").read_text()
    step = spec.split("6. **§4, the fallback.**", 1)[1].split("\n7. ", 1)[0]
    assert "the database is unchanged by it" not in step
    assert "sets the database back to that copy" in flat(step)


def test_t533_5_section_4_states_the_risks_under_argo_cd_before_step_1() -> None:
    """The operator's decision of 2026-10-02: the two risks Argo CD brings to a restore are stated at the top of §4,
    with the lab's numbers, and step 5 no longer says the recovery pod stops "at once" (#532)."""
    body = section("4")
    assert "> **Risks under Argo CD**" in body and body.index("> **Risks under Argo CD**") < body.index("1. **Turn it on")
    risks = flat("\n".join(line for line in body.splitlines() if line.startswith(">")))
    for words in ("selfHeal: true", "0.7 s", "4 min 38 s", "Pause automated sync first", "12 min 49 s", "limit: 3",
                  "less than 0", "retries 5 times", "#532", "§4d step 7"):
        assert words in risks, words
    step5 = flat(body.split("5. **Turn it off**", 1)[1].split("\n\n", 1)[0])
    assert "stops at once" not in step5, "under a retrying sync the recovery pod does not stop at once (#532)"
    for words in ("#532", "12 min 49 s", "known limitation"):
        assert words in step5, words


def test_t533_6_section_4d_pauses_first_and_gives_the_release_back_to_git() -> None:
    """§4d, the break glass: the pause comes first and is confirmed, with the operation's phase beside it, before the
    hand edit; the restore is the script; the give-back waits for Argo CD's apply before `oc rollout status`, and
    ends with what the edit added removed. §4d is §4's last subsection, because T300-10 exempts it whole."""
    body = section("4")
    assert re.findall(r"^### (4\w)\. ", body, re.M) == ["4a", "4b", "4c", "4d"]
    glass = body.split("### 4d.", 1)[1]
    code = code_lines(glass)
    steps = [
        r"argocd\.argoproj\.io/tracking-id",
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
    for step in steps:
        hits = [i for i, line in enumerate(code) if step in line]
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

### Block 18 — local-development/prepare-release.py: a spec id may have two digits

T533-8 (Orchestrator's notes, 5): E10's row must be read when 3.0.0 is cut.

<!-- block: local-development/prepare-release.py | edit -->

Old text:

```text
_INDEX_MERGED = re.compile(
    r"^(?P<pre>\| (?P<id>[A-Z]\d[a-z]?) \| \[`(?P<file>SPEC_[A-Za-z0-9_]+\.md)`\]\([^)]+\)"
```

New text:

```text
# An id is a batch letter, a number of any length (E10, #533) and a step letter or none (S4a).
_INDEX_MERGED = re.compile(
    r"^(?P<pre>\| (?P<id>[A-Z]\d+[a-z]?) \| \[`(?P<file>SPEC_[A-Za-z0-9_]+\.md)`\]\([^)]+\)"
```

### Block 19 — local-development/tests/test_prepare_release.py: T533-8, a two-digit id in the promotion test

<!-- block: local-development/tests/test_prepare_release.py | edit -->

Old text:

```text
        "| Z2 | [`SPEC_Z2_example.md`](SPEC_Z2_example.md) — example | Z | — | chart 9.0.0 |"
        " [#2](https://github.com/ephico2real2/group-sync-dashboard/issues/2) | in progress |\n"
    )
    for name, status in (("SPEC_Z1_example.md", "merged"), ("SPEC_Z2_example.md", "in progress")):
```

New text:

```text
        "| Z2 | [`SPEC_Z2_example.md`](SPEC_Z2_example.md) — example | Z | — | chart 9.0.0 |"
        " [#2](https://github.com/ephico2real2/group-sync-dashboard/issues/2) | in progress |\n"
        # a two-digit id (E10, #533): a row the pattern cannot read leaves its merged header behind, and the release
        # is refused
        "| Z10 | [`SPEC_Z10_example.md`](SPEC_Z10_example.md) — example | Z | — | chart 9.0.0 |"
        " [#3](https://github.com/ephico2real2/group-sync-dashboard/issues/3) | merged |\n"
    )
    for name, status in (("SPEC_Z1_example.md", "merged"), ("SPEC_Z2_example.md", "in progress"),
                         ("SPEC_Z10_example.md", "merged")):
```

### Block 20 — local-development/tests/test_prepare_release.py: T533-8, the two-digit row and header are released

<!-- block: local-development/tests/test_prepare_release.py | edit -->

Old text:

```text
    assert re.search(r"\| Z2 \|.*\| in progress \|$", index, re.M)
```

New text:

```text
    assert re.search(r"\| Z2 \|.*\| in progress \|$", index, re.M)
    assert re.search(r"\| Z10 \|.*\| released \|$", index, re.M)
    assert "| Status | released |" in (specs / "SPEC_Z10_example.md").read_text()
```

### Block 21 — local-development/tests/test_restore_db.py: the undo test runs §4a's body from the new command line

The test executes the body of §4a's `oc debug` command as the runbook prints it; it finds the command by its first
line, which block 8 changes.

<!-- block: local-development/tests/test_restore_db.py | edit -->

Old text:

```text
    start = next(i for i, line in enumerate(lines) if line.startswith("oc debug -n $NS deploy/$REL -c dashboard -- sh -c '"))
```

New text:

```text
    start = next(i for i, line in enumerate(lines)
                 if line.startswith("oc debug -n $NS deploy/$REL --one-container -c dashboard -- sh -c '"))
```
