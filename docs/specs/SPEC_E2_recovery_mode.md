# SPEC E2 — recovery mode: the dashboard pod with its data volume mounted and the app stopped, for a restore (#303)

| | |
|---|---|
| Programme | Epic E (#385), restore tools and release safety; build-order step 1 of 9 (#302's restore script runs inside this pod) |
| Batch | E — restore tools and release safety |
| Release | — (post-programme; Epic E's release, milestone 3.0.0) |
| Version on release | chart 0.60.0 (chart only) |
| Version note | No application version: the recovery program ships in the chart as a ConfigMap (the issue's decision 1), so nothing under `publish.yml`'s image paths changes. The chart takes a MINOR, 0.59.25 to 0.60.0, because it adds two values and a template (`Chart.yaml`'s own rule: "MAJOR and MINOR for behaviour"). If another chart change lands first, block 11 fails its check because its Old text is the version it replaces; the implementing pull request then takes the next free MINOR and corrects blocks 11, 14 and 18 (the three that name 0.60.0) here before applying (`docs/specs/README.md`, "Implementation blocks") |
| Issue | [#303](https://github.com/ephico2real2/group-sync-dashboard/issues/303) |
| Status | specified |
| Source | OB1-lite's research and specification of 2026-10-01, written before any code from the issue (its "Decisions and corrections (2026-10-01)"), the epic's "Decisions settled (2026-10-01)" and the Epic E mock (PR #504). Measured on main `5c03a9b1` (application 2.0.0, chart 0.59.25) with helm v4.3.0 and Python 3.14.7 on this machine, and read-only on the CRC lab (OpenShift 4.22.7, Kubernetes v1.35.6, Argo CD v3.4.7). §7's blocks were cut from a copy of `5c03a9b1` with the design implemented, and proved against a clean tree (§4.3). Revised the same day on the reviews of `b7b8e993` (OB3 in Grok's seat, Codex gpt-5.6-sol xhigh) and the operator's rules of 2026-10-01, re-cut from origin/main `dd51b91f` and proved again (§4.3) |

## How to read this spec

**The point in one sentence: one chart value, `recovery.enabled`, turns the dashboard pod into a pod that holds
the data volume with the app stopped, keeps itself out of the Service, survives a dropped `oc` session, and ends
itself, visibly, after `recovery.ttl`.**

§1 is the mandate. §2 is the research: each finding names its primary source, the exact sentence relied on, and
what it settles; lab reads carry the command and its output. §2a weighs the alternatives and reconciles each
external claim with the code that relies on it. §3 is the design, one decision per subsection, with
the safety budgets. §4 maps every test case of the issue (T303-1 to T303-19) to a test and shows each failing on a
tree without the change. §5 is the walk the implementing pull request runs on the lab. §6 is what an operator sees
and what it costs. §7 is the whole change as implementation blocks (`docs/specs/README.md`, "Implementation
blocks"), applied to a clean tree with

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_E2_recovery_mode.md . --apply

Citations into the code use `path#anchor`; upstream sources are named with their URL and the commit or tag they
were read at, and their line numbers are written as plain text (`curl -s <raw-url> | nl -ba`). This spec's own
row in the index moves through the lifecycle by the orchestrator's hand; no block touches it. A block found wrong
during implementation is corrected here, with the reason under the orchestrator's notes, before it is applied
again.

## Orchestrator's notes

Decisions taken while specifying, on "easy to manage, best practice", and the corrections the research made to
the issue, the epic and the mock. Each is applied in §3 and §7 and held by a test in §4.

1. **Correction: "no existing alert fires in recovery mode" holds for the dashboard's own rules, not for
   all of them.** The issue's correction 2 and the epic's decision of 2026-10-01 say no alert fires and the
   TTL is the bound. `GroupSyncDashboardNotPolling` indeed returns nothing: its gauge comes from the stopped
   process (§2.10). But `GroupSyncDashboardReportSnapshotStale` (warning) reads
   `gsd_report_snapshot_age_seconds`, which the **report service** emits
   (`local-development/gsd/reporting/metrics.py#gsd_report_snapshot_age_seconds`), and the report pod keeps
   running in recovery mode while the copies it reads stop advancing, because the dashboard's leader writes
   them (`local-development/gsd/poller.py#_maybe_report_snapshot`). With reporting on and the rules on (both
   default), it fires once the newest copy is older than four snapshot intervals (4 × 300 s) for `for.reportSnapshot`
   (30m): about 50 minutes into recovery mode, inside the default 2h TTL. Not measured live (monitoring
   validation is parked on CRC). The values comment, the chart README, the runbook and the CHANGELOG say both
   facts. The issue's option (a) stands, no new rule: the TTL is the bound.
2. **Readiness is a dedicated `tcpSocket` probe on the container's own `http` port, rendered whatever
   `probes.readiness.enabled` says.** The issue's correction 1 relied on the existing `httpGet` probe through
   the proxy, which fails while uvicorn is down. That probe renders only when `probes.readiness.enabled` is on
   (`charts/group-sync-dashboard/templates/deployment.yaml#{{- if .Values.probes.readiness.enabled }}`), and
   with it off the pod would be Ready at once (§2.2) and join the Service. A TCP probe on 8080 cannot pass
   while nothing listens, needs no `exec` (the probe page warns of exec's process cost) and does not depend on
   `oauthProxy.skipAuthRegex`. Not measured: whether the oauth-proxy sidecar logs every failed upstream request
   (Go's `ReverseProxy` does by default, §2.2); the TCP probe does not reach the proxy, so the question does not
   arise. T303-4 is parametrized over `probes.readiness.enabled` true and false. With the proxy off the pod has
   one container and reads `0/1`, not `1/2` (rendered: every recovery-on combination of `oauthProxy.enabled` and
   both probe switches carries the probe, and none carries a sidecar probe, a readiness gate or
   `publishNotReadyAddresses`).
3. **The TTL is kept in the pod's `/tmp`, so it survives a container restart (the mandate's question).** The
   kubelet restarts an exited container at once the first time and resets its back-off after ten minutes of
   running (§2.1). A TTL counted from each start would therefore expire, restart at once and sleep another full
   TTL: no CrashLoopBackOff, ever. The script writes `$TMPDIR/gsd-recovery.json` (the chart's `tmp` emptyDir at
   `/tmp`) on the pod's first start and reads it back on every later start; an emptyDir outlives a container
   crash and goes with the pod (§2.3). After the deadline every start exits 1 at once, which is what keeps the
   pod in CrashLoopBackOff. The budget is per pod: a new pod gets a new emptyDir and a new TTL, whether it comes
   from a new `recovery.ttl`, `oc delete pod`, an eviction, a node drain or a node lost (§3.6). And the script
   is the container's PID 1, so at the TTL the kernel ends every process in the container with it, an
   `oc exec` restore still running included (§2.4, measured); the runbook says to check the time left before a
   restore. The time left is counted on the node's monotonic clock, not the wall clock, so setting the clock back
   cannot lengthen it (Codex F1; §2.11, §3.6). #302 reads the same file for its "too little TTL left" refusal (the
   epic's decision of 2026-10-01); its fields are in §3.5.
4. **The issue's test wording, aligned with the mock.** T303-9 says the *first line* names the mode, the TTL,
   the time left, the idle sentence and the data path; the mock (block 1 of `docs/design/restore-cli-mock.html`
   on main since PR #504) prints them as a four-line banner, and the spec follows the mock: T303-9 reads the
   first four lines, and a fifth says to check the time left before a restore (OB3's F2). T303-10 says the *last line* names the command to extend; the mock prints the reason first
   and the commands after it. The spec keeps both: the reason first, then what to change, then a last line that
   repeats the reason and names `recovery.ttl` and `recovery.enabled: false` in the release's values file, so
   `oc logs --tail=1` still answers.
5. **Where the spec differs from the mock, and why.** (a) Times left print as a compact Go duration (`2h`,
   `1h30m`), not `2h0m`, because the same function writes the suggested `recovery.ttl`, which must parse.
   (b) The mock's command lines (the Argo CD Application patches and `helm upgrade --reuse-values`) are not
   printed anywhere: the operator's direction of 2026-10-01 makes the release's values file the only path
   (note 6). (c) "To leave: remove both parameters" becomes "set `recovery.enabled: false` in the release's
   values file and roll it out", which keeps everything else in that file, a rollback's `image.tag` included.
   (d) The log names nothing but the values file: the reviewed draft's `oc delete pod` line is gone from it
   (the operator's rule covers "any message a program prints"); the runbook keeps it as a pod action. (e) The mock's caption "it never opens the database" and "1/2" ready are kept as they are.
6. **The only path is the release's values file (the operator, 2026-10-01).** "Be careful with over
   complicating the argocd — we might be using applicationset in production and certain parameters are fixed.
   whatever things needs to happen to be supported by Helm values file directly. Argocd is just a conduit —
   don't complicate it." And: "In a real enterprise — nobody uses manual cli to work on argocd or helm. we are
   only using the cli and --set options only for troubleshooting and development." The review measured why the
   earlier Application-patch path was unsafe (§2.8): a JSON merge patch replaces the whole `parameters` list,
   so the printed patches dropped a rollback's `image.tag` (the app would have restarted on the chart's default
   image, not the one rolled back to, against the epic's flow "the same target image starts the app") and the
   four image parameters `release-crc.sh --argocd` writes on the lab; and an ApplicationSet with its default
   `sync` policy overwrites a hand patch of the Application it generates. So the script's log, the values
   comment, the chart README, the runbook and the CHANGELOG name the values file and the release's deployment
   pipeline, and nothing else. Argo CD is named only to say why a hand edit of the Deployment is reverted; a
   plain `helm upgrade -f` appears once, on the runbook's line for development and troubleshooting. Held by
   T303-10 and `test_the_only_documented_path_is_the_values_file`.
7. **The offsite claim, checked against the CronJob's own mount (the epic's decision of 2026-10-01).** The
   recovery pod mounts it read-only at `/offsite` exactly when the CronJob renders with a `pvc` destination, by
   the same switch and the same claim name
   (`charts/group-sync-dashboard/templates/backup-offsite.yaml#claimName: {{ $o.destination.pvc.existingClaim | default (printf "%s-backup-offsite" $fullname) }}`).
   The CronJob mounts it read-write; the claim the chart creates is `ReadWriteOnce`
   (`charts/group-sync-dashboard/templates/backup-offsite.yaml#$o.destination.pvc.accessMode | default "ReadWriteOnce"`),
   which "can allow multiple pods to access …
   that volume when the pods are running on the same node" (§2.6). With the default `ReadWriteMany` data volume
   the CronJob has no affinity to the dashboard's node (`backup-offsite.yaml#{{- if ne $mode "ReadWriteMany" }}`),
   so on a multi-node cluster a run scheduled on another node while the recovery pod holds the claim waits on
   the attachment, and the recovery pod, started while a run holds it elsewhere, waits for that run to end. A
   `ReadWriteOncePod` destination admits one pod at a time. The cost is bounded and harmless: nothing new is
   written to `/data/backup` while the app is stopped, so a run that waits ships nothing it would have shipped.
   Not measured (the lab is one node and has no offsite CronJob). Decided: mount it as the epic decided, and say
   this in the values comment's terms ("read-only at /offsite").
8. **#304 must carry this mount's switch.** The mount reads `.Values.backup.offsite.enabled`, as the CronJob does
   today. #304 makes that switch three-state with one helper deciding for the CronJob and the alerts (the epic's
   decision); its spec must use the same helper for `$offsiteClaim` in `deployment.yaml` (block 3), or recovery
   mode stops mounting a claim the CronJob renders. A test holds the two together:
   `test_the_offsite_claim_is_mounted_exactly_when_the_cronjob_writes_one` compares the mount with the CronJob's
   claim in five value sets, so a #304 that turns offsite on by default without the mount fails it (§4.2, C8),
   where the earlier `test_no_offsite_mount_without_a_pvc_destination` still passed.
9. **`recovery.enabled` is read as a word; `.Values.recovery` is read nil-safe.** A `--set-string` `"false"` is
   a non-empty string, which a template `if` takes as true, and turning recovery on stops the dashboard: the
   helper accepts `true` and `false` and refuses anything else by name. And `helm upgrade --reuse-values` onto
   this chart from 0.59.x renders with the old chart's values, where `recovery` does not exist (§2.7): the
   helpers default the block to empty, so that render is the default one (held by T303-14).
10. **No upper bound on the TTL.** The operator sets it in an incident and may need a long restore; a cap would
    be one more refusal to fight at 03:00. The default (2h) bounds the forgotten case, and every extension is a
    deliberate values change.
11. **The lab runs the image under emulation, and qemu-user does not change the SIGTERM rule.** PID 1 of the
    lab's dashboard container is `/usr/bin/qemu-x86_64-static /usr/sbin/python3.14 -m uvicorn …` on an `arm64`
    node (§2.9): the amd64 image runs under qemu-user. Measured on a podman machine of the same shape (arm64
    Linux, `qemu-x86_64-static` in binfmt_misc, the published amd64 2.0.0 image; on the host PID 1 reads
    `/usr/bin/qemu-x86_64-static /usr/sbin/python3.14 …`, `NSpid … 1`): the script as PID 1 stops 0.19 s after
    SIGTERM with exit 0 under qemu (0.17 s natively), and a control with no handler waits out the 10 s grace and
    dies by SIGKILL, exit 137, under both (§2.4). The walk (§5, step 6) still times the stop on the lab.
12. **The index.** This spec adds the thirty-sixth row, at the end like D5's (#244) because it is the last to be
    specified, and `local-development/tests/test_specs_index.py` excludes #303 from the rising-issue check as it
    does #244. A spec for #239 is being written from the same main in parallel; whichever merges second rebases
    the count sentence and the test's count.
13. **A GitOps sync waits for the recovery rollout (read from the code, not measured).** This chart's syncs
    are multi-step (`charts/group-sync-dashboard/templates/secrets-mint.yaml#argocd.argoproj.io/hook: PreSync`),
    and in a multi-step sync Argo CD v3.4.7 keeps the operation running until every applied resource is Healthy
    or Degraded (`gitops-engine/pkg/sync/sync_context.go` lines 556-580, `multiStep` in `sync_tasks.go` lines
    274-276); a Deployment is Degraded only at `ProgressDeadlineExceeded` (`health_deployment.go` lines 37-42),
    600 s after the recovery rollout starts. Meanwhile auto-sync starts nothing (`controller/appcontroller.go`
    lines 2241-2244), and the running operation and its retries keep the revision it started with
    (`controller/sync.go` lines 124-145; a retry clears only the sync result, `appcontroller.go` lines 1532-1536).
    So a values change committed within about ten minutes of the one that turned recovery on is applied only
    after that sync fails and its retries end. The docs say only what holds for any pipeline (a step that waits
    for the rollout reports it failed); the walk measures the delay (§5, step 7).

14. **The reviews of `b7b8e993` (2026-10-01), decided by the orchestrator, each traced before it was applied.**
    - **OB3, accepted whole:** (1) the release's values file as the only path, in blocks 1, 10, 12, 13, 14, 18,
      19, 20 and the prose (notes 5-6, §2.8, §3.9, §5, §6); (2) at the TTL every process in the container stops,
      a restore included (measured 4.2 s in), so the runbook and the banner say to check the time left first, and
      the TTL budget is per pod (an eviction, a drain or a lost node starts a new one); (3) READY reads `0/1`
      with the proxy off; (4) `test_the_offsite_claim_is_mounted_exactly_when_the_cronjob_writes_one` replaces
      `test_no_offsite_mount_without_a_pvc_destination`, so #304 cannot separate the mount from the CronJob;
      (5) §3.7's `ttl: null` (it renders `2h`), §4.3's checksum line, note 11 measured, note 13, and the
      alternatives, now §2a. Changed after it: the script's `oc delete pod` line is dropped (note 5), so its
      `--namespace` argument is dropped with it (blocks 1, 4 and the T303-1 command).
    - **Codex F1 (HIGH), accepted:** the deadline was wall-clock only, so a backward step lengthened the TTL. The
      fix counts the time left on the node's monotonic clock and records the node's boot ID (§2.11, §3.6). Taken
      from Codex: the boot ID and refusing a record without the monotonic fields. Not taken: Codex's minimum of
      the wall and monotonic deadlines (the wall clock adds nothing to a bound the monotonic clock already
      holds), and the coordinator's proposal of a cap alone (`min(deadline - now, ttl)`), which still lets each
      backward step buy up to a TTL; the cap is kept as a guard inside `remaining`. The premise "monotonic clocks
      reset across container restarts" is refuted by measurement: in the lab pod `time.monotonic()` read 120743 s
      against a container started 66378 s after the node's boot, and the pod is in the initial time namespace
      (§2.11).
    - **Codex F3 (MEDIUM), accepted:** `ne (int .Values.replicaCount) 1` let `replicaCount: true` through
      (`int true` is 1) and rendered `replicas: true`; the guard compares `toString` with `"1"` (block 3), and
      T303-5 renders `true`.
    - **Codex F2, superseded** by the operator's rules (no Argo CD command anywhere); its sub-point, a `250ms`
      TTL suggesting `0s`, is taken: the suggestion is at least `1s`
      (`test_the_suggested_ttl_is_a_positive_duration_for_a_subsecond_ttl`). **Codex F4** (the runbook's
      undefined `<chart>`, the unconditional `1/2`) is closed by the values-file path and OB3's (3). Codex's
      corrected blocks were not taken, because they still print Argo CD and `--set` commands.
15. **What #302 (SPEC E3) takes from here, after this revision.** Unchanged: the environment names
    (`GSD_RECOVERY_MODE`, `GSD_RECOVERY_MODE_TTL`), the file `/tmp/gsd-recovery.json` and its fields `ttl`,
    `started`, `started_epoch`, `deadline`, `deadline_epoch`, the offsite mount at `/offsite`, and the per-pod
    TTL. Added to the file: `deadline_monotonic` and `boot_id`, which the time left is counted from (§3.5); a
    reader that wants this script's own answer computes `deadline_monotonic - time.monotonic()` when `boot_id`
    matches the node's, and 0 otherwise. Removed: the script's `--namespace` argument (no reader).

**Open questions for the operator.** None.

## 1. The mandate, and what is out of scope

The issue (#303, "What must be accomplished"): one chart value turns recovery mode on and off; with it on, the
dashboard container runs a small recovery program instead of uvicorn on the same pod spec and data volume, with
`GSD_RECOVERY_MODE=true` and `GSD_RECOVERY_MODE_TTL`, with the proxy on or off; no liveness probe and no ready
Service endpoint; the render refuses `replicaCount` other than 1, a TTL that is not a duration or is zero, and
`persistence.enabled=false`; the program never opens the database and imports neither `gsd.store` nor `sqlite3`;
its log says what the pod is and counts down; at the TTL it exits non-zero, so the pod shows CrashLoopBackOff, and
names the command that extends it; it stops within a second of SIGTERM as PID 1; it works under the image a
rollback targets; everything else renders as before (RBAC ADDED 0, REMOVED 0); on the lab the pod outlives 11
minutes with nothing holding `/data/gsd.db` and the app comes back on the same database; the runbook, `values.yaml`
and the chart README describe it truthfully. The epic adds: the recovery pod mounts the offsite claim read-only
when `backup.offsite` uses a `pvc` destination, and it is set through the release's values or the Application's
parameters, never `oc set env`. The operator's direction of 2026-10-01 narrows that last point: the release's
values file, rolled out through the release's deployment pipeline, is the only path, and "the command that
extends it" is that values change (Orchestrator's notes, 6).

Out of scope, each owned elsewhere: the restore itself (listing, checking and writing a copy) is #302; the
release note's schema line and the runbook's §0 are #300; offsite on by default is #304; the KPI backup card is
#306. A new alert for recovery mode is not added (Orchestrator's notes, 1).

## 2. Research, measured

Kubernetes documentation is read at kubernetes/website `607898ad64b369bc3e533c9d45d450f8d03f8a0b` (main on
2026-10-01; the lab runs v1.35.6), Helm's at helm/helm-www `a00848f704284ff9300c1bcc356c3638309a53ce` and helm/helm
`v4.3.0` (the version on this machine), Argo CD's at argoproj/argo-cd `v3.4.7` (the lab's, `argocd version
--client --short` in its server pod). Each raw file was fetched with `curl` on 2026-10-01 and its line numbers
read with `nl -ba`.

### 2.1 What the kubelet does when the container exits

**Source.** `content/en/docs/concepts/workloads/pods/pod-lifecycle.md`, "How Pods handle problems with
containers", lines 203-211: "**Initial crash**: Kubernetes attempts an immediate restart based on the Pod
`restartPolicy`." … "**Repeated crashes**: After the initial crash Kubernetes applies an exponential backoff delay
for subsequent restarts" … "**Backoff reset**: If a container runs successfully for a certain duration (e.g., 10
minutes), Kubernetes resets the backoff delay, treating any new crash as the first one." Lines 386-389: "the kubelet
restarts them with an exponential backoff delay (10s, 20s, 40s, …), that is capped at 300 seconds (5 minutes). Once
a container has executed for 10 minutes without any problems, the kubelet resets the restart backoff timer for that
container." A Deployment's pods take `restartPolicy: Always` (line 296: "the only allowed value").

The feature gates that change the numbers: `KubeletCrashLoopBackOffMax` is beta and on by default from 1.35
(`feature-gates/KubeletCrashLoopBackOffMax.md`: "configurable per-node backoff maximums"), and
`ReduceDefaultCrashLoopBackOffDecay` is alpha and off (1s initial, 60s maximum when on). On the lab the kubelet's
`/configz` (`oc get --raw /api/v1/nodes/crc/proxy/configz`) reads `'crashLoopBackOff': {'maxContainerRestartPeriod':
'5m0s'}`.

**What it settles.** A TTL counted from each container start is not a TTL: at its end the container exits, is
restarted at once, and, having run longer than ten minutes (any TTL above that, the default 2h included), starts
again with no back-off and sleeps another full TTL. The deadline must outlive the container (§3.6). After the deadline, a container that exits within a second of
every start stays in the back-off, whatever the delays are: that is the CrashLoopBackOff the issue wants visible.

### 2.2 Probes: a missing readiness probe is Ready

**Source.** `content/en/docs/concepts/workloads/pods/probes.md`, lines 205-207: "If a container does not provide a
particular probe, the kubelet always considers the result as `Success`. For readiness probes specifically, the
result is considered `Failure` before the initial delay." Lines 194-199: "For readiness probes, the kubelet marks the
container as not ready, and the Pod stops receiving traffic from matching Services." Lines 170-174: `tcpSocket`
"Performs a TCP check against the Pod's IP address on a specified port. The diagnostic is considered successful if
the port is open." Lines 177-183 caution that an `exec` probe involves "the creation/forking of multiple processes
each time when executed". Line 260 (`failureThreshold`): "For a failed readiness probe, the kubelet continues running
the container that failed checks … the kubelet sets the `Ready` condition on the Pod to `false`." `oc explain
pod.spec.containers.readinessProbe.tcpSocket.port` on the lab: "Number or name of the port to access on the
container."

The oauth-proxy sidecar has no probe (`charts/group-sync-dashboard/templates/deployment.yaml#- name: oauth-proxy`
onwards carries none), so with the dashboard container not ready the pod is `1/2` and not a ready endpoint. Go's
`net/http/httputil/reverseproxy.go` at `go1.25.0`, lines 319-321: `defaultErrorHandler` runs `p.logf("http: proxy
error: %v", err)`; whether openshift/oauth-proxy replaces that handler was not read.

**What it settles.** Recovery mode must render a readiness probe of its own, whatever `probes.readiness.enabled`
says, and it must be one that cannot pass while nothing listens: a TCP probe on the dashboard container's own port
`http` (8080). The liveness probe is dropped: a failed liveness probe "triggers a restart" (line 260), which is the
kill mid-restore the issue exists to prevent.

### 2.3 The pod's `/tmp` outlives a container restart

**Source.** `content/en/docs/concepts/storage/volumes.md`, lines 163-171: "For a Pod that defines an `emptyDir`
volume, the volume is created when the Pod is assigned to a node. … When a Pod is removed from a node for any reason,
the data in the `emptyDir` is deleted permanently." and "A container crashing does *not* remove a Pod from a node. The
data in an `emptyDir` volume is safe across container crashes." The chart already mounts an emptyDir named `tmp` at
`/tmp` in the dashboard container
(`charts/group-sync-dashboard/templates/deployment.yaml#readOnlyRootFilesystem is on, so anything writing to /tmp needs a volume`);
the lab pod shows it (`('tmp', '/tmp', False)` in the mount list,
§2.9), empty, writable, and `TMPDIR` unset.

**What it settles.** `/tmp` keeps the deadline across restarts of the container and loses it with the pod, which is
the lifetime the TTL needs (§3.6).

### 2.4 SIGTERM and a Python PID 1

**Source.** pid_namespaces(7) (man7.org, Linux man-pages 6.19, 2026-05-13): "Only signals for which the "init"
process has established a signal handler can be sent to the "init" process by other members of the PID namespace.
… Likewise, a process in an ancestor namespace can … send signals to the "init" process of a child PID namespace
only if the "init" process has established a handler for that signal." And: "If the "init" process of a PID
namespace terminates, the kernel terminates all of the processes in the namespace via a SIGKILL signal."
Kubernetes, pod-lifecycle.md lines 854-856: the kubelet asks the runtime to stop the containers "by first sending
a TERM (aka. SIGTERM) signal, with a grace period timeout, to the main process in each container." Python,
`Doc/library/signal.rst` (cpython 3.14) lines 17-22: "A small number of default handlers are installed: `SIGPIPE`
is ignored … and `SIGINT` is translated into a `KeyboardInterrupt` exception". Measured: `python -c 'import
signal; print(signal.getsignal(signal.SIGTERM))'` on Python 3.14.7 prints `0` (`SIG_DFL`). `Doc/library/time.rst`
lines 390-391: "If the sleep is interrupted by a signal and no exception is raised by the signal handler, the sleep
is restarted with a recomputed timeout." So a handler that raises ends the sleep at once.

**Measured as PID 1, natively and under qemu.** A podman machine on this Mac (arm64 Linux, with
`qemu-x86_64-static` registered in binfmt_misc, the lab's shape) ran the script as each container's PID 1 with a
read-only root, `/tmp` and `/scripts` as volumes and a non-root UID with group 0, and stopped it as the runtime
stops a pod's container (`podman stop -t 10`: SIGTERM from the host, SIGKILL at the grace period). The published
amd64 2.0.0 image ran under qemu (on the host its PID 1 reads `/usr/bin/qemu-x86_64-static /usr/sbin/python3.14 …`,
`NSpid … 1`); the lab's own arm64 2.0.0 build ran natively:

| PID 1 | stop after SIGTERM | exit | last line |
|---|---|---|---|
| the script, native | 0.17 s | 0 | `SIGTERM: stopping (exit 0); the app was not running` |
| the script, qemu | 0.19 s | 0 | the same |
| a `time.sleep` with no handler, native | 10.18 s (the grace) | 137 (SIGKILL) | — |
| a `time.sleep` with no handler, qemu | 10.15 s (the grace) | 137 (SIGKILL) | — |

Under qemu the host's view of PID 1 has no SIGTERM bit in `SigCgt` (`0x7000004de`): qemu-user installs no handler
of its own for a guest signal left at its default, so the kernel's rule applies unchanged. A second run started a
30-second loop through `podman exec` (what `oc exec` does) two seconds into a 6-second TTL: when the script exited
at the TTL the loop died with it, exit 137 after 4.2 s, 4 of its 30 lines written.

**What it settles.** A Python PID 1 with no SIGTERM handler does not receive the kubelet's SIGTERM and is killed
only at the end of the grace period (30 s on the lab, §2.9), natively and under qemu-user. The script installs a
handler that raises, so `recovery.enabled=false` (Recreate stops the recovery pod first) does not wait out the
grace period. And the script's own exit at the TTL ends every process in the container, a restore running
through `oc exec` included: the runbook tells the operator to check the time left first (block 14).

### 2.5 A script in a ConfigMap, run by any UID

**Source.** volumes.md line 137: "A ConfigMap is always mounted as `readOnly`." The chart's precedent ships
`scripts/offsite_backup.py` in a ConfigMap
(`charts/group-sync-dashboard/templates/backup-offsite.yaml#{{ .Files.Get "scripts/offsite_backup.py" | indent 4 }}`)
and a test holds it verbatim
(`local-development/tests/test_chart_backup_offsite.py#test_the_configmap_carries_the_script_verbatim`). On the lab
(`oc exec … -c dashboard -- python3.14 -c …`): `uid 1000790000 gid 0 groups [0, 1000790000]`, `python 3.14.7`,
`/scripts exists: False`, SCC `restricted-v2` (`openshift.io/scc` annotation), and `PYTHONUNBUFFERED=1`,
`PYTHONDONTWRITEBYTECODE=1` in the image (`local-development/Containerfile#PYTHONUNBUFFERED=1`).

**Measured under the image a rollback targets.** The script, streamed into the lab's running 2.0.0 pod and run
without touching anything (`--help` exits before any work; `-X importtime` lists every import):

    $ oc exec -i -n group-sync-dashboard deploy/group-sync-dashboard -c dashboard -- python3.14 -X importtime - --help < recovery_mode.py
    exit=0
    usage: - [-h] [--release RELEASE] [--namespace NAMESPACE]
             [--report-every REPORT_EVERY]
    102 modules imported; sqlite3/_sqlite3/gsd present: []

and its parser and formatter, exec'd as a module (not as `__main__`):
`[7200.0, 5400.0, 5400.0, None, 0.0] 1h30m 1970-01-01T00:00:00Z` for `2h`, `90m`, `1h30m`, `abc`, `0s`.

**What it settles.** A stdlib script mounted read-only at `/scripts` (mode 0444) and run as `python3.14
/scripts/recovery_mode.py` works under the published 2.0.0 image, as any UID, with no write to its own directory,
and imports neither `sqlite3` nor `gsd`. It does what the issue's decision 1 needs.

### 2.6 A claim mounted by two pods, read-only by one

**Source.** `content/en/docs/concepts/storage/persistent-volumes.md`, lines 625-640: "`ReadWriteOnce` the volume can
be mounted as read-write by a single node. ReadWriteOnce access mode still can allow multiple pods to access (read
from or write to) that volume when the pods are running on the same node." "`ReadWriteOncePod` … if you want to
ensure that only one pod across the whole cluster can read that PVC or write to it." Lines 664-668: "Volume access
modes do **not** enforce write protection once the storage has been mounted." volumes.md lines 1204-1208: a
`volumeMounts[].readOnly` mount "does not make the volume itself read-only, but that specific container will not be
able to write to it." `oc explain pod.spec.volumes.persistentVolumeClaim.readOnly` on the lab: "readOnly Will force
the ReadOnly setting in VolumeMounts. Default false."

**What it settles.** The recovery pod sets both (`persistentVolumeClaim.readOnly` and the mount's `readOnly`), as the
CronJob does for the data claim (`backup-offsite.yaml#readOnly: true`), so the recovery shell cannot write the
offsite copies. Read-only does not change the attachment: a `ReadWriteOnce` offsite claim is still one node's at a
time (Orchestrator's notes, 7).

### 2.7 Helm: `fail`, and what `--reuse-values` renders with

**Source.** helm-www `docs/chart_template_guide/function_list.mdx`, lines 184-188: `fail` "Unconditionally returns an
empty `string` and an `error` with the specified text. This is useful in scenarios where other conditionals have
determined that template rendering should fail." helm/helm `v4.3.0`, `pkg/action/upgrade.go`, lines 614-626 (`func
(u *Upgrade) reuseValues`): "If the ReuseValues flag is set, we always copy the old values over the new config's
values." … `oldVals, err := util.CoalesceValues(current.Chart, current.Config)` … `chart.Values = oldVals`. `helm
upgrade --help` (v4.3.0): `--reset-then-reuse-values` "when upgrading, reset the values to the ones built into the
chart, apply the last release's values and merge in any overrides from the command line via --set and -f". The
chart README (`charts/group-sync-dashboard/README.md#A values FILE is the better habit anyway`): with `-f` or
`--set` Helm "resets to chart defaults plus what this invocation supplied".

**What it settles.** Every refusal is a `fail` in the render, as the chart's other guards are. A release upgraded to
this chart with `--reuse-values` renders with the previous chart's defaults, where `recovery` does not exist, so the
helpers read it nil-safe. The spec prints no Helm command for an operator (Orchestrator's notes, 6); the runbook's
one plain-Helm line, for development and troubleshooting, passes the release's complete values file with `-f`.

### 2.8 Argo CD and ApplicationSets: why a hand edit is reverted, and why a patched Application is not a path

**Source.** argo-cd `v3.4.7` `docs/user-guide/helm.md`, line 48 and lines 398-400: "Order of precedence is
`parameters > valuesObject > values > valueFiles > helm repository values.yaml`"; lines 381-396: `argocd app set
helm-guestbook -p service.type=LoadBalancer`, and declaratively `source.helm.parameters: [{name, value}]`.
`docs/user-guide/auto_sync.md`, lines 3-4: "Argo CD has the ability to automatically sync an application when it
detects differences between the desired manifests in Git, and the live state in the cluster"; lines 78-79: "By
default, changes that are made to the live cluster will not trigger automated sync. To enable automatic sync when
the live cluster's state deviates from the state defined in Git" (self-heal); lines 118-121: "Automated sync will
only attempt one synchronization per unique combination of commit SHA1 and application parameters" and "If the
`selfHeal` flag is set to true, then the sync will be attempted again after self-heal timeout (5 seconds by
default)". `pkg/apis/application/v1alpha1/types.go`, lines 620-633 (`AddParameter`): "If a parameter with the same
name already exists, its value will be overwritten. Otherwise, the HelmParameter will be appended as a new entry",
which `argocd app set -p` calls (`cmd/util/app.go`, line 541). `docs/user-guide/commands/argocd_app_unset.md`, line
43: `-p, --parameter stringArray  Unset a parameter override`. RFC 7396 (rfc-editor.org), §1 and §2: "Null values in the
merge patch are given special meaning to indicate the removal of existing values in the target" and "it is not
possible to patch part of a target that is not an object, such as to replace just some of the values in an array."
Kubernetes, `update-api-object-kubectl-patch.md` lines 218-220: "With a JSON merge patch, if you want to update a
list, you have to specify the entire new list. And the new list completely replaces the existing list", and line
528: "Strategic merge patch is not supported for custom resources." The ApplicationSet controller, argo-cd `v3.4.7`
`docs/operator-manual/applicationset/Controlling-Resource-Modification.md`, lines 143-145: "When an ApplicationSet is
reconciled, the controller will compare the ApplicationSet spec with the spec of each Application that it manages.
If there are any differences, the controller will generate a patch to update the Application to match the
ApplicationSet spec"; lines 21 and 38: the `--policy` default is `sync`, under which "Create, Update and Delete are
allowed"; lines 104-105: only an `ignoreApplicationDifferences` rule exempts a field, and lines 147-148: the
controller's patch is a merge patch, so "existing lists will be completely replaced by new lists".

**Measured against what the earlier draft printed.** RFC 7396's own algorithm (§2 pseudocode), applied to the exact
JSON the draft's script printed at the TTL (the review of 2026-10-01 ran it; the harness is not committed):

- the lab's Application after `release-crc.sh --argocd`, which writes four image parameters
  (`local-development/release-crc.sh#apply_application()`): the draft's "turn on" patch left only the two
  recovery parameters, so the dev-built images fell back to the chart's default, and its "leave" patch removed
  the list;
- the epic's rollback entered as the draft's runbook said ("set the older `image.tag` in the same change"), i.e.
  `image.tag` in the same list: the draft's "extend" patch dropped `image.tag`, and its "leave" patch
  (`"parameters": null`) restarted the app on the chart's default image instead of the target, against the
  epic's "Set recovery.enabled=false: the same target image starts the app".

**What it settles.** Recovery mode is a value in the release's values file, rolled out through the release's
deployment pipeline (Orchestrator's notes, 6): it holds the rollback's `image.tag` and `recovery` in one place, a
leave changes only `recovery.enabled`, and it works the same whether the conduit is Helm, an Application or an
ApplicationSet. A hand edit of the Deployment (`oc set env`, `oc scale`) is exactly what self-heal reverts; a hand
patch of an ApplicationSet-generated Application is overwritten by the ApplicationSet controller. Neither is a path,
and nothing the chart or the script prints proposes one.

### 2.9 The lab, read-only, 2026-10-01

    $ oc get applications.argoproj.io -n openshift-gitops group-sync-dashboard -o json   (fields read with python)
    labels: None
    annotations keys: ['argocd.argoproj.io/sync-options', 'kubectl.kubernetes.io/last-applied-configuration']
    ownerReferences: None
    helm keys: ['releaseName', 'valueFiles', 'valuesObject']
    parameters: None
    syncPolicy: {"automated": {"prune": true, "selfHeal": true}, "retry": {…}, "syncOptions": [...]}
    targetRevision: main
    sync: Synced health: Healthy

No parent Application or ApplicationSet tracks it (no labels, no owner). The parameters read `None` because the last
deploy took `release-crc.sh`'s branch path; an `--argocd` deploy at a pushed head writes four image parameters onto
it (`local-development/release-crc.sh#apply_application()`). Neither matters to recovery mode, which is set in the
values file the Application reads (Orchestrator's notes, 6).

    $ oc get deploy -n group-sync-dashboard group-sync-dashboard -o json   (fields read with python)
    replicas 1 strategy Recreate progressDeadline 600 terminationGrace 30
    dashboard quay.io/ephico2real/group-sync-dashboard:2.0.0 cmd: ['python3.14', '-m', 'uvicorn', 'gsd.api:create_app', '--factory', '--host', '127.0.0.1', '--port', '8080', '--workers', '1'] live: True ready: True
      mounts: [('config', '/etc/gsd', True), ('data', '/data', False), ('tmp', '/tmp', False), ('curlrc', '/etc/curl', True), ('report-token', '/etc/gsd/report', True), ('service-ca', '/etc/gsd/service-ca', True), ('trusted-ca-injected', '/etc/pki/ca-trust/extracted/pem/injected', True)]
    oauth-proxy registry.redhat.io/openshift4/ose-oauth-proxy-rhel9:v4.15 cmd: None live: False ready: False
    $ oc get pvc -n group-sync-dashboard
    group-sync-dashboard-data               f065b7a4-535c-4ef1-868c-58f5afee4953   [ReadWriteMany]   crc-csi-hostpath-provisioner   Bound
    group-sync-dashboard-report-artifacts   08c7d45c-a3eb-47be-8506-f24ea7a3e0e3   [ReadWriteOnce]   crc-csi-hostpath-provisioner   Bound
    $ oc get pdb -n group-sync-dashboard
    group-sync-dashboard          N/A   1   1
    $ oc get node crc -o jsonpath='{.status.nodeInfo.architecture} {.status.nodeInfo.kubeletVersion}'
    arm64 v1.35.6
    $ oc exec -n group-sync-dashboard deploy/group-sync-dashboard -c dashboard -- python3.14 -c '…'
    id uid 1000790000 gid 0 groups [0, 1000790000]
    python 3.14.7
    /scripts exists: False
    /tmp entries: []
    TMPDIR: None
    PID1 cmdline: /usr/bin/qemu-x86_64-static /usr/sbin/python3.14 -m uvicorn gsd.api:create_app --factory --host 127.0.0.1 --port 8080 --
    tmp writable: True
    GSD env: ['GSD_CONFIG', 'GSD_DB_PATH', 'GSD_ENABLE_VIEW_RESTRICTIONS', 'GSD_GIT_BRANCH', 'GSD_GIT_COMMIT', 'GSD_HTTP_LOG_LEVEL', 'GSD_LOG_LEVEL', 'GSD_TRUSTED_CA_FILE', 'GSD_VERSION']

The lab has no offsite CronJob and one node. The PDB is `maxUnavailable: 1`, so a drain still evicts a not-ready
recovery pod (the default `unhealthyPodEvictionPolicy` evicts a running, not-ready pod while the budget is met; not
measured), and the replacement pod starts a new TTL (§3.6).

### 2.10 What alerts while the app is stopped

Read from `charts/group-sync-dashboard/templates/monitoring.yaml` (every `expr:`):

| rule | reads | in recovery mode |
|---|---|---|
| `GroupSyncDashboardNotPolling` | `(time() - gsd_cluster_last_poll_timestamp_seconds)`, emitted by the dashboard (`local-development/gsd/metrics.py#gsd_cluster_last_poll_timestamp_seconds`) | the series stops; an expression over a missing series returns nothing: **does not fire** |
| `GroupSyncDashboardBackupStale`, the WAL pair, `GroupSyncClusterUnreachable`, the `gsd_alerts_total` rules, `GroupSyncDashboardReportUsagePullFailing` | gauges and counters of the dashboard process | the same: **do not fire** |
| `GroupSyncDashboardReportSnapshotStale` | `gsd_report_snapshot_age_seconds > 4 × reporting.snapshot.intervalSeconds`, emitted by the **report service** (`local-development/gsd/reporting/metrics.py#gsd_report_snapshot_age_seconds`); rendered only with `reporting.enabled` | the report pod runs on; the newest copy stops advancing: **fires** after 1200 s plus `for.reportSnapshot` (30m) at the defaults, about 50 minutes |
| `GroupSyncDashboardPodThrottled`, `…PodMemoryHigh`, `…VolumeDiskFull` | the KPI self-report, `component` labelled | the report pod's series continue; the dashboard's stop |
| the two offsite rules | `kube_cronjob_status_last_successful_time` | unchanged by recovery mode |

Not measured live: monitoring validation is parked on CRC (`docs/specs/README.md`, "Monitoring, parked"). Cluster
rules outside the chart (the platform's own) were not read.

### 2.11 The clock the TTL is counted on

**Source.** clock_gettime(2) (man7.org, Linux man-pages 6.19, 2026-03-07): "`CLOCK_MONOTONIC` A nonsettable
system-wide clock that represents monotonic time since … "some unspecified point in the past". On Linux, that point
corresponds to the number of seconds that the system has been running since it was booted. The `CLOCK_MONOTONIC`
clock is not affected by discontinuous jumps in the system time (e.g., if the system administrator manually changes
the clock)". random(4): `boot_id` is a read-only file holding a random string that "was generated once". Python,
`Doc/library/time.rst` (cpython 3.14) lines 289-303: `monotonic()` is "a clock that cannot go backwards. The clock
is not affected by system clock updates", and on Linux it calls `clock_gettime(CLOCK_MONOTONIC)`.

**Measured in the lab pod** (`oc exec … -c dashboard -- python3.14 -c …`, read-only):

    boot_id: 1e78896e…
    monotonic: 120743 uptime: 120743.03
    pid1 start (s since boot): 66378
    time ns: /proc/self/ns/time time:[4026531834]
    pid1 time ns: time:[4026531834]

The container started 66378 s after the node booted, and its monotonic clock reads the node's 120743 s: it is the
node's clock, not reset by a container (re)start. The pod is in the initial time namespace (the same inode as PID 1
of the container; no per-container offset).

**What it settles.** The time left is `deadline_monotonic - time.monotonic()`, which a wall-clock step cannot move
and a container restart does not reset. Only a node restart resets it; the boot ID says when that happened, and
then the time left cannot be measured and counts as reached (§3.6). The wall clock is used only to print instants.

## 2a. Alternatives considered

The issue's original description names what the current path gets wrong ("the debug pod is tied to the terminal",
"it is a different pod spec", "`--replicas=0` then `debug` is two states to get wrong"). Each alternative, its
source, and the chart code it meets:

| alternative | the source says | against this chart | decided |
|---|---|---|---|
| `oc scale --replicas=0`, then `oc debug deploy/…` (today's §4a) | `oc debug --help` (oc 4.22.13): "The started pod will be a copy of your source pod, with labels stripped, the command changed to '/bin/sh' …, and readiness and liveness checks disabled"; "The debug pod is deleted when the remote command completes or the user interrupts the shell"; `--preserve-pod`: "If true, the pod will not be deleted after the debug command exits" | the copy has no labels, so the Service, which selects by `gsd.selectorLabels` (`charts/group-sync-dashboard/templates/service.yaml#selector: {{- include "gsd.selectorLabels"`), sends it nothing, and no probe kills it. But the writer is stopped by `oc scale`, a hand edit of `replicas: {{ .Values.replicaCount }}` (`charts/group-sync-dashboard/templates/deployment.yaml#replicas: {{ .Values.replicaCount }}`), which self-heal reverts (§2.8), starting the writer on a half-restored file; without `--preserve-pod` a dropped session deletes the pod; it has no TTL; and it is two manual CLI steps | kept as the fallback (the issue's Definition of Done), not the primary path |
| `kubectl debug <pod> --copy-to=…` | kubernetes/website `debug-running-pod.md` lines 471-477: "you can use `kubectl debug` to create a copy of the Pod with configuration values changed"; lines 518-522: "Don't forget to clean up the debugging Pod"; kubectl `v1.35.0` `profiles.go` lines 204-210: the `general` profile's copy removes labels, annotations, probes and init containers (the default profile is still `legacy`, `debug.go` line 217) | the copy outlives the session, but it copies a running pod: the writer still has to be stopped by hand, with the same self-heal problem; a bare pod has no controller, so an eviction ends it; no TTL | rejected |
| a separate recovery Job, the Deployment at 0 replicas | `job.md` lines 769-771: "The `activeDeadlineSeconds` applies to the duration of the job, no matter how many Pods are created. Once a Job reaches `activeDeadlineSeconds`, all of its running Pods are terminated and the Job status will become `type: Failed` with `reason: DeadlineExceeded`" | the one alternative with a stronger bound: its deadline survives a pod replaced by an eviction, which the per-pod deadline of §3.6 does not. Against it: a second pod spec beside the Deployment's (the issue's "different pod spec" defect, or a refactor of `deployment.yaml` into a shared helper); a Job's pod template is immutable, so a new TTL needs a new Job name, as the bind Job does (`charts/group-sync-dashboard/templates/backup-offsite.yaml#a Job's pod template is`); and a running Job is `Progressing` to Argo CD until it ends (`gitops-engine/pkg/health/health_job.go` lines 54-57), so this chart's multi-step syncs (Orchestrator's notes, 13) would wait the whole TTL rather than 600 s | rejected; recorded as the design to take if the per-pod bound proves too weak |
| an ephemeral container | `ephemeral-containers.md`: "Ephemeral containers may not have ports, so fields such as `ports`, `livenessProbe`, `readinessProbe` are disallowed"; "they will never be automatically restarted" | it joins a running pod, whose app is the writer: it cannot hold the volume with the writer stopped | rejected |
| the Deployment's own pod, its command swapped (this spec) | §2.1 to §2.6 | the same pod spec, volumes, UID and image as the app; Recreate stops the writer first; no new object but a ConfigMap; one value in the release's values file turns it on and off through any conduit | chosen |

**Reconciliation: each external claim the design relies on, and the code that behaves accordingly.**

| research says | this repository does it at |
|---|---|
| the kubelet restarts an exited container at once and resets its back-off after ten minutes of running (§2.1) | the deadline is written once per pod and read back on every start, `charts/group-sync-dashboard/scripts/recovery_mode.py#deadline` (block 1) |
| an emptyDir survives a container crash and goes with the pod (§2.3) | it is written under `$TMPDIR`, the chart's `tmp` emptyDir at `/tmp` (`charts/group-sync-dashboard/templates/deployment.yaml#readOnlyRootFilesystem is on, so anything writing to /tmp needs a volume`) |
| `CLOCK_MONOTONIC` is system-wide, counts from the boot and ignores clock changes; `boot_id` is fixed per boot (§2.11) | the time left is `remaining`, `deadline_monotonic - time.monotonic()` with a boot-ID check (`charts/group-sync-dashboard/scripts/recovery_mode.py#remaining`, block 1) |
| a container without a readiness probe is `Success`; `tcpSocket` passes only when the port is open (§2.2) | the recovery probe is a TCP probe on `http`, rendered whatever `probes.readiness.enabled` says (block 7), on a container whose command binds nothing (block 4) |
| a namespace's PID 1 receives only the signals it has a handler for; Python installs none for SIGTERM (§2.4) | the script installs its own, `charts/group-sync-dashboard/scripts/recovery_mode.py#_on_sigterm` (block 1), and it is PID 1 because the command runs `python3.14` directly (block 4) |
| a ConfigMap is always mounted read-only (§2.5) | the script runs as `python3.14 /scripts/recovery_mode.py` and writes nothing beside itself (block 1), from a ConfigMap at mode 0444 (block 8), as `charts/group-sync-dashboard/templates/backup-offsite.yaml#.Files.Get "scripts/offsite_backup.py"` ships its precedent |
| `ReadWriteOnce` admits pods on one node; a read-only mount does not change the attachment (§2.6) | the offsite claim is mounted with `persistentVolumeClaim.readOnly` and a read-only mount, the claim name being the CronJob's own (block 8; `charts/group-sync-dashboard/templates/backup-offsite.yaml#claimName: {{ $o.destination.pvc.existingClaim`) |
| `fail` stops the render; `--reuse-values` renders with the previous chart's values (§2.7) | the refusals are `fail`s (block 3) and the helpers read `recovery` nil-safe (block 2) |
| a GitOps tool's self-heal reverts a hand edit of a rendered object (§2.8) | the only path the docs and the script name is the values file (blocks 1, 10, 12, 13, 14, 18), held by `test_the_only_documented_path_is_the_values_file` |

## 3. The design

### 3.1 The switch

`recovery.enabled` (default `false`) and `recovery.ttl` (default `2h`), read through two helpers in
`_helpers.tpl`: `gsd.recoveryEnabled` returns `true` or `false` and refuses any other word, and `gsd.recoveryTtl`
returns the TTL as typed, `2h` when the key is absent, never through `default` (which would turn `ttl: 0` into
`2h`). Both default the block to an empty dict (Orchestrator's notes, 9). `deployment.yaml` computes `$recovery`
once, beside the chart's other guards, and every recovery branch reads it.

The default stays off under the 0.14.0 rule: turning it on stops the dashboard. `recovery.enabled` joins
`KEPT_OFF` in `local-development/tests/test_values_defaults.py` with that reason.

### 3.2 The command

With `$recovery`, the dashboard container's `command` is

    python3.14 /scripts/recovery_mode.py --release <release name>

in place of the chart's uvicorn command (proxy on) **and** of the image's `CMD` (proxy off): the branch comes first
in an `if / else if .Values.oauthProxy.enabled`, so the proxy's setting cannot leave uvicorn in force. The script is
the chart's `scripts/recovery_mode.py`, carried by a ConfigMap `<fullname>-recovery`
(`templates/recovery.yaml`, rendered only while recovery is on) and mounted read-only at `/scripts` with mode 0444
(`defaultMode: 292`, the decimal form this file uses for its other modes). The release name is an
argument only so the lines it prints at the TTL name the release whose values file to change.

### 3.3 The environment

`GSD_RECOVERY_MODE=true` and `GSD_RECOVERY_MODE_TTL=<recovery.ttl>`, appended after the container's existing
variables. Every other variable stays, `GSD_DB_PATH` included, so the script prints the path the app would open
(`/data/gsd.db` at one replica). #302's wrapper reads `GSD_RECOVERY_MODE` to know it is in recovery mode (the mock's
block 3).

### 3.4 The probes

No liveness probe (§2.2). A readiness probe of its own, rendered whatever `probes.readiness.enabled` says:

    readinessProbe: {tcpSocket: {port: http}, periodSeconds: 30, timeoutSeconds: 5, failureThreshold: 1}

`http` is the dashboard container's own port (8080, declared on that container, so the name resolves there).
Nothing listens on it while the script runs, so the probe never passes and the pod is never a ready endpoint of
the Service or the Route. The sidecar has no probe and is ready, so the pod reads `1/2`; with the proxy off there
is no sidecar and it reads `0/1`. A pod is Ready only when all its containers are (pod-lifecycle.md line 611,
"`ContainersReady`: all containers in the Pod are ready"), so the sidecar cannot make it Ready. The Deployment
never reports an available replica, so a pipeline step that waits for the rollout reports it failed: `helm upgrade
--wait` times out, and Argo CD shows the Deployment Progressing, then Degraded after `progressDeadlineSeconds` (600 s
on the lab), an honest signal for a pod that serves nothing (and see the Orchestrator's notes, 13).

### 3.5 The script

`charts/group-sync-dashboard/scripts/recovery_mode.py`, standard library only (block 1). In order:

1. Installs a SIGTERM handler that raises `_Stop` (§2.4), inside the `try` that turns `_Stop` into the line
   `SIGTERM: stopping (exit 0); the app was not running` and exit 0.
2. Parses `GSD_RECOVERY_MODE_TTL` with the grammar of `gsd.durationSeconds` (one regular expression, the same units,
   `µs` included). Not a positive duration: one line and exit 2. The render already refused it (§3.7); this is the
   script's own guard for a hand-made pod.
3. Reads or writes the deadline (§3.6). A file it cannot read or write: one line naming the file and exit 2,
   never a fresh TTL, because a fresh TTL on every failure would never end.
4. Prints the banner, four lines, each prefixed with an ISO-8601 UTC instant and `gsd-recovery` (the mock's):

        2026-10-01T09:47:30Z gsd-recovery RECOVERY MODE (GSD_RECOVERY_MODE=true, GSD_RECOVERY_MODE_TTL=2h)
        2026-10-01T09:47:30Z gsd-recovery the app is NOT running and no data is collected
        2026-10-01T09:47:30Z gsd-recovery data path /data/gsd.db (not opened by this process)
        2026-10-01T09:47:30Z gsd-recovery TTL 2h: ends 2026-10-01T11:47:30Z, 2h left

   After a container restart the fourth line adds `(kept from this pod's first start at <instant>; the container
   restarted)`. A fifth line follows: `check the time left before a restore: at the TTL this process exits and
   every process in the container stops with it`.
5. Sleeps to the deadline in steps of `--report-every` seconds (1800 by default, the mock's half hour), printing
   `<left> left; the app is NOT running and no data is collected` after each step that ends before the deadline.
6. At the deadline prints the reason, what to change, and a summary line, then exits 1. What to change is a value
   in the release's values file, rolled out through the release's deployment pipeline; no command line at all
   (Orchestrator's notes, 5 and 6):

        2026-10-01T11:47:30Z gsd-recovery TTL 2h reached at 2026-10-01T11:47:30Z; exiting 1: the app is still NOT running and no data is collected
        2026-10-01T11:47:30Z gsd-recovery to extend: set a longer recovery.ttl (for example 4h) in release group-sync-dashboard's values file and roll it out through its deployment pipeline; the new pod counts it from its start
        2026-10-01T11:47:30Z gsd-recovery to leave: set recovery.enabled: false in release group-sync-dashboard's values file and roll it out; the app starts on /data/gsd.db
        2026-10-01T11:47:30Z gsd-recovery TTL 2h reached; exiting 1. Extend with recovery.ttl, leave with recovery.enabled: false, in the release's values file (lines above)

   The suggested TTL is twice the current one, at least `1s`, printed as a Go duration so it can be pasted. When
   the node restarted under the pod, a line before the reason says so (§3.6). The script is the
   container's PID 1, so its exit ends every process in the container (§2.4).

It never reads `GSD_DB_PATH` except to print it: it opens, stats and creates nothing under the data directory, and
imports neither `sqlite3` nor `gsd` (T303-8 seals the directory with mode 000 and runs it with `-X importtime`; the
review ran the same under the published 2.0.0 image, to the TTL, with no import of either). Every print flushes,
so `oc logs` shows each line as it is written whatever the image's buffering.

**The deadline file, the contract #302 reads.** `$TMPDIR/gsd-recovery.json` (`/tmp/gsd-recovery.json` in the pod),
one JSON object: `ttl` (as typed), `started` and `deadline` (ISO-8601 UTC to the second), `started_epoch` and
`deadline_epoch` (seconds since the epoch, float; for display), `deadline_monotonic` (the node's `CLOCK_MONOTONIC`
at the deadline, float) and `boot_id` (the node's, from `/proc/sys/kernel/random/boot_id`; empty off Linux). The
time left is `deadline_monotonic - time.monotonic()` while `boot_id` matches, never more than the TTL, and 0 when
it does not. Written once per pod, to `gsd-recovery.json.tmp` and then renamed, so a kill mid-write leaves no half
file; a record missing a field, or carrying a number that is not finite, is refused (exit 2), never replaced.

### 3.6 The TTL across restarts, and CrashLoopBackOff

The budget: **at most one TTL of running per pod, counted from the pod's first container start, whatever the number
of container restarts; after it, every container start exits 1 within a second.** A pod keeps one TTL value for its
life (`GSD_RECOVERY_MODE_TTL` is in the pod template, so a new value is a new pod), so "per (pod, TTL value)" and
"per pod" are the same bound. Its scope is the pod: a new pod has a new emptyDir and a new TTL, whether it comes from
a new `recovery.ttl` (it changes the pod template), `oc delete pod`, an eviction (a node drain: the PDB's
`maxUnavailable: 1` allows it, §2.9) or a node lost ("When a Pod is removed from a node for any reason, the data in
the `emptyDir` is deleted permanently", §2.3). So the TTL bounds each pod, not recovery mode: a forgotten recovery
mode crash-loops until a person turns it off, and runs another TTL after each replacement of its pod. Deleting
`/tmp/gsd-recovery.json` by hand inside the pod also restarts it at the next container start; that is a deliberate
act and is not guarded.

**The clock (Codex F1).** Within one pod the bound holds whatever the wall clock does: the time left is counted on
the node's `CLOCK_MONOTONIC`, which a clock change does not move and a container restart does not reset (§2.11), and
it is never more than the TTL. A backward step of the wall clock therefore buys nothing, and a forward one ends
nothing early. The one event that resets the monotonic clock, a node restart with the pod kept, changes the boot ID,
and the time left then counts as 0: the TTL ends early rather than late. Measured by
`test_a_backward_wall_clock_step_cannot_lengthen_the_ttl` (a record whose wall-clock deadline is an hour away but
whose monotonic deadline has passed exits 1 at once) and `test_a_node_restart_under_the_pod_counts_as_the_ttl_reached`.

| event in one pod | what the script does |
|---|---|
| first start | writes the deadline = now + TTL; banner; waits |
| container restart before the deadline (OOM, a kill, a node hiccup that keeps the pod) | reads the same deadline; banner says "kept from this pod's first start"; waits for the rest |
| the deadline | prints the reason and what to change; exit 1; every process in the container ends with it, an `oc exec` restore included (§2.4) |
| every start after the deadline | banner (`0s left`), the reason and what to change at once; exit 1 within a second |
| a deadline file it cannot use (corrupt, empty, unreadable, a directory, a key missing, a number not finite) | one line naming the file; exit 2 at every start, never a fresh TTL |
| the wall clock set back or forward | nothing: the time left is on the monotonic clock |
| the node restarted, the pod kept (another boot ID) | the TTL counts as reached: a line says so, then the reason; exit 1 |
| SIGTERM at any point | `SIGTERM: stopping (exit 0)`; exit 0 at once |

With §2.1's kubelet, the first exit at the deadline is restarted at once and exits at once; the next restarts wait
10 s, 20 s, 40 s … up to 300 s (the lab's `maxContainerRestartPeriod`), and the pod reads `CrashLoopBackOff` with its
restart count rising. It never runs ten minutes, so the back-off never resets. Measured here by the unit tests (a
second start in the same `$TMPDIR` keeps the deadline; a start after it exits 1 in under a second), by the review
against every shape of deadline file (each unusable one exits 2 at once, a kept one waits only the rest) and under
the published 2.0.0 image (a restart after the deadline exits 1 in 0.69 s under qemu); the CrashLoopBackOff itself
is the lab walk's (§5, step 5).

### 3.7 The refusals

All in the render, before any object is applied, each naming the value:

| when `recovery.enabled=true` and | message starts | why |
|---|---|---|
| `replicaCount` is not 1 (0, 2 and `true` included; compared as text, because `int true` is 1, Codex F3) | `recovery.enabled=true requires replicaCount: 1 (it is N)` | one pod holds the volume; at 0 there is none, and a second is a second writer on `ReadWriteMany` or a Pending pod on `ReadWriteOnce(Pod)` |
| `persistence.enabled=false` | `recovery.enabled=true requires persistence.enabled=true` | an emptyDir has nothing to restore onto and is wiped with the pod (the shape of `backup-offsite.yaml#backup.offsite.enabled=true requires persistence.enabled=true`) |
| `recovery.ttl` is not a Go duration (`abc`, `-5m`, `7200`, `2H`, `1 h`) | `recovery.ttl "…" is not a duration` | parsed by the existing `gsd.durationSeconds` (`-1`), the issue's decision 4 |
| `recovery.ttl` is zero (`0`, `0s`, `0.0s`, `0h0m`) | `recovery.ttl "…" is zero` | the pod would exit at once and crash-loop |
| (any) `recovery.enabled` is not `true` or `false` | `recovery.enabled "…" is not true or false` | Orchestrator's notes, 9 |

`recovery.ttl: null`, in a values file or as `--set recovery.ttl=null`, is not refused: Helm removes a key set to
null before the template reads it, so the TTL is the default `2h` (rendered both ways: `GSD_RECOVERY_MODE_TTL: "2h"`).

`strategy` needs no rule of its own: with persistence on and one replica the chart derives `Recreate`, and an
explicit `RollingUpdate` is already refused there
(`charts/group-sync-dashboard/templates/deployment.yaml#strategy=RollingUpdate is unsafe at replicaCount 1 with persistence enabled`).
So the writer is gone before the recovery pod starts, and the recovery pod is gone
before the app starts again.

### 3.8 The offsite claim

When `backup.offsite.enabled` and `backup.offsite.destination.type` is `pvc`, the recovery pod mounts the same claim
the CronJob writes (`destination.pvc.existingClaim`, else `<fullname>-backup-offsite`) at `/offsite`, with
`persistentVolumeClaim.readOnly: true` and a read-only mount. With the `s3` destination or offsite off, nothing more
is mounted. The access-mode consequences are in the Orchestrator's notes, 7; the switch's future in 8.

### 3.9 Setting it

In the release's values file, rolled out through the release's deployment pipeline like any other value; for a
rollback, the older `image.tag` goes in the same change (Orchestrator's notes, 6). Never `oc set env` or an edit of
the Deployment: a GitOps tool's self-heal reverts it (§2.8). The runbook's §4 gives the steps (block 14) and one
plain `helm upgrade -f` line, labelled for development and troubleshooting. Turning it off is the reverse, in the
same file: `recovery.enabled: false`, keeping a rollback's `image.tag`. When the change is applied, Recreate stops
the recovery pod (in under a second, §2.4) and starts the app on the restored file.

### 3.10 What alerts

As §2.10 and the Orchestrator's notes, 1. The values comment says, plainly: nothing is recorded; no rule says
recovery mode; `GroupSyncDashboardNotPolling` does not fire; with reporting on
`GroupSyncDashboardReportSnapshotStale` fires after about 50 minutes; the TTL is the bound. No document claims
`NotPolling` covers recovery mode (T303-19).

### 3.11 Versions

Chart 0.60.0, a MINOR (two values and a template). `appVersion` stays 2.0.0 and the image does not change, so no
application bump (`publish.yml`'s paths are untouched). The CHANGELOG entry sits under `## Unreleased` and names
chart 0.60.0, which `local-development/tests/test_kyverno.py#test_f3_unreleased_cites_the_current_chart_version_when_it_moved_since_the_last_release`
requires.

### 3.12 What does not change

With `recovery.enabled=false` (or absent): the rendered manifests, apart from the chart version and the two values
computed from it, the pod's `checksum/config` (it hashes the ConfigMap, chart label included) and, with offsite on,
the bind Job's name (it hashes `.Chart.Version`); every chart release moves those three, so an upgrade to 0.60.0
restarts the dashboard pod once, as every chart upgrade does (T303-14 in the tree; the cross-commit form is §4.3). With it on: every object except the dashboard Deployment and
the new ConfigMap is identical, the report Deployment, the offsite CronJob, every claim, the Service, the Route and
the oauth-proxy container included; the Deployment's metadata, selector, strategy, replicas and pod template
metadata (labels, `checksum/config`) are identical too (T303-15). RBAC: ADDED 0, REMOVED 0, on and off (T303-16 and
§4.3). The application, its image and its tests are untouched.

## 4. Tests

### 4.1 One test per issue test case

`local-development/tests/test_recovery_mode.py` (block 19) runs the script as the pod does, as a separate process;
`local-development/tests/test_chart_recovery_mode.py` (block 20) renders the chart with `helm template`, as the
chart's other render tests do.

| ID | test | fails without the change because |
|---|---|---|
| T303-1 | `test_t303_1_recovery_runs_the_chart_script_on_the_same_volume_with_the_env` | `recovery.enabled` is ignored: the render with it is byte-identical to the default (measured, §2) and the command is `gsd.api:create_app` |
| T303-2 | `test_t303_2_recovery_overrides_the_image_cmd_with_the_proxy_off_too` | with the proxy off the chart sets no `command` at all, so the image's uvicorn `CMD` stays |
| T303-3 | `test_t303_3_no_liveness_probe_in_recovery_mode` | the liveness probe renders whenever `probes.liveness.enabled` |
| T303-4 | `test_t303_4_a_readiness_probe_that_cannot_pass_keeps_the_pod_out_of_the_service[true, false]` | there is no recovery probe; with `probes.readiness.enabled=false` there is no readiness probe at all, and a missing one is `Success` (§2.2) |
| T303-5 | `test_t303_5_more_than_one_replica_is_refused` | no recovery guard: `replicaCount=2` (and 0, and `true`) renders |
| T303-6 | `test_t303_6_a_ttl_that_is_not_a_positive_duration_is_refused[abc, -5m, 7200, 0, 0s]` | no `recovery.ttl` value exists |
| T303-7 | `test_t303_7_recovery_without_a_volume_is_refused` | no recovery guard |
| T303-8 | `test_t303_8_it_imports_neither_the_store_nor_sqlite3_and_touches_nothing_in_the_data_directory` | no script exists (`charts/group-sync-dashboard/scripts/` holds only `offsite_backup.py`) |
| T303-9 | `test_t303_9_the_log_says_what_the_pod_is_then_counts_down_in_utc` | as T303-8 |
| T303-10 | `test_t303_10_at_the_ttl_it_exits_1_and_says_how_to_extend_or_leave_through_the_values_file` | as T303-8; it also fails on a log that prints a Helm or Argo CD command line or an Application patch (the earlier draft's, mutation R7) |
| T303-11 | `test_t303_11_sigterm_stops_it_at_once_through_its_own_handler` | as T303-8. Exit 0 with the line, not `-15`, is what proves the handler: a child (not PID 1) dies at once under the default action too. The PID-1 behaviour itself is §2.4's measurement |
| T303-12 | `test_t303_12_every_import_is_from_the_standard_library` (also parses the script with `feature_version=(3, 11)`, the floor CI tests) | as T303-8 |
| T303-13 | the lab walk, §5 step 2 (the published 2.0.0 image); measured read-only already, §2.5, and to the TTL under that image by the review, §3.5 | — |
| T303-14 | `test_t303_14_off_renders_exactly_the_default_and_the_dashboard_as_today` (default = `recovery.enabled=false` = `recovery=null`) | a regression guard; it passes at the merge base too |
| T303-15 | `test_t303_15_nothing_but_the_dashboard_container_and_its_volumes_changes[default, offsite]` | the recovery ConfigMap does not appear (the issue had this as a guard that passes vacuously; it also asserts the new object, so it fails before) |
| T303-16 | `test_t303_16_no_rbac_rule_is_added_or_removed`, and the rule diff in §4.3 | a regression guard |
| T303-17, T303-18 | the lab walk, §5 steps 3 and 7 | — |
| T303-19 | `test_t303_19_the_docs_name_the_switch_and_say_what_alerts` | no recovery text exists; it also holds the values file and the pipeline as the way to set it, what the TTL ends, the per-pod TTL and the `0/1` without the proxy |

Added by the research and the design:

| test | holds |
|---|---|
| `test_the_ttl_survives_a_container_restart_and_an_expired_one_exits_at_once` | §3.6: a second start in the same `$TMPDIR` keeps the deadline; a start after it exits 1 in under a second |
| `test_a_deadline_file_that_cannot_be_read_exits_2_rather_than_restart_the_clock[not-json, no-monotonic-deadline, nan]` | §3.5 step 3 |
| `test_a_backward_wall_clock_step_cannot_lengthen_the_ttl` | §3.6, the clock (Codex F1) |
| `test_a_node_restart_under_the_pod_counts_as_the_ttl_reached` | §3.6, the boot ID |
| `test_the_suggested_ttl_is_a_positive_duration_for_a_subsecond_ttl` | §3.5 step 6 (Codex F2's sub-point) |
| `test_a_ttl_that_is_not_a_positive_duration_exits_2[…]` | §3.5 step 2 |
| `test_the_duration_grammar_and_the_printed_spans` | the parser and the formatter |
| `test_the_switch_is_read_as_a_word` | Orchestrator's notes, 9 |
| `test_the_configmap_carries_the_script_verbatim` | §3.2, the offsite precedent |
| `test_the_offsite_claim_is_mounted_read_only_as_the_cronjob_names_it[default claim, existingClaim]` | §3.8 |
| `test_the_offsite_claim_is_mounted_exactly_when_the_cronjob_writes_one[default, off, pvc, existing-claim, s3]` | §3.8 and the Orchestrator's notes, 8: the mount and the CronJob's claim agree in every value set, so #304's default cannot separate them |
| `test_the_chart_and_the_script_accept_the_same_ttls[…]` | one grammar in two places: the render accepts a TTL exactly when the script parses it as positive |
| `test_the_only_documented_path_is_the_values_file` | the Orchestrator's notes, 6: no Application patch, parameter, `argocd` or Helm command line in the values comment, the chart README, the runbook's operator steps or the CHANGELOG; Argo CD named only beside "revert"; one `helm upgrade -f`, on the runbook's development-and-troubleshooting line |
| `test_the_only_false_defaults_are_the_stated_exceptions` (existing, block 21) | `recovery.enabled` is a stated exception |

### 4.2 Each test fails without the change, and mutations

**On a clean tree of origin/main `dd51b91f`, before the blocks**, with the two new test modules copied in and run
with `PYTHONPATH` at that tree's `local-development`: `51 failed, 5 passed in 3.29s`. The five that pass: the two
regression guards the issue says pass at the merge base, `test_t303_14_off_renders_exactly_the_default_and_the_dashboard_as_today`
and `test_t303_16_no_rbac_rule_is_added_or_removed`, and three cases of
`test_the_offsite_claim_is_mounted_exactly_when_the_cronjob_writes_one` (`default`, `off`, `s3`), which hold
vacuously: with no feature there is no mount, and in those three value sets no CronJob writes a claim. Every other
test fails for the reason §4.1 gives: the script tests on `can't open file … recovery_mode.py` (the process exits 2
with empty stdout) or `FileNotFoundError` reading it; the render tests on the ignored value (`KeyError: 'command'`
with the proxy off, `httpGet` where `tcpSocket` is expected, `'livenessProbe' not in …` false, `assert (not True)`
where a refusal is expected, `set() == {('ConfigMap', 't-group-sync-dashboard-recovery')}`, a mount list `[]` where
the CronJob writes a claim); the documentation tests on the missing text. **After `--apply`:** `56 passed in
11.91s`. **On the reviewed draft's blocks (`b7b8e993`) applied to `dd51b91f`:** `11 failed, 45 passed`, the eleven
being T303-1 (its command still carried `--namespace`), T303-5 (`replicaCount=true` rendered), T303-9 (no line to
check the time left), T303-10 (Argo CD patches and `--set` in the log), T303-19,
`test_the_only_documented_path_is_the_values_file`, the clock and boot-ID tests, the sub-second extension, and the
two new deadline-file shapes (no monotonic deadline, `NaN`).

**Mutations of the implemented copy**, each run against the module that holds it (a scratch copy per row; the
imported script and chart are the mutated ones):

| run | the change | result | tests that go red |
|---|---|---|---|
| R0 | none | 18 passed | — |
| R1 | no SIGTERM handler | 1 failed | `test_t303_11_…` (exit `-15`, not 0) |
| R2 | the deadline not read back (every start a new TTL) | 6 failed | the restart test, the clock and boot-ID tests, the three unreadable-file cases |
| R3 | `import sqlite3` added | 2 failed | `test_t303_8_…`, `test_t303_12_…` |
| R4 | exit 0 at the TTL | 6 failed | `test_t303_10_…`, `test_t303_8_…`, the restart, clock, boot-ID and extension tests |
| R5 | `os.stat` on the database path | 8 failed | `test_t303_8_…` (the sealed directory), and the seven that run it with no data directory |
| R6 | no countdown lines | 1 failed | `test_t303_9_…` |
| R7 | the time left read from the wall clock (the reviewed draft's) | 1 failed | `test_a_backward_wall_clock_step_cannot_lengthen_the_ttl` |
| R8 | no boot-ID check | 1 failed | `test_a_node_restart_under_the_pod_counts_as_the_ttl_reached` |
| R9 | an Argo CD patch printed at the TTL | 1 failed | `test_t303_10_…` |
| R10 | the suggested TTL not bounded below (`250ms` suggests `0s`) | 1 failed | `test_the_suggested_ttl_is_a_positive_duration_for_a_subsecond_ttl` |
| C0 | none | 38 passed | — |
| C1 | the liveness probe kept in recovery mode | 1 failed | `test_t303_3_…` |
| C2 | the recovery probe only when `probes.readiness.enabled` | 1 failed | `test_t303_4_…[false]` |
| C3 | `replicaCount` through `int` (the reviewed draft's) | 1 failed | `test_t303_5_…` (`true` renders) |
| C4 | no persistence guard | 1 failed | `test_t303_7_…` |
| C5 | no zero-TTL guard | 4 failed | `test_t303_6_…[0]`, `[0s]`, and the parity test `[0]`, `[0s]` |
| C6 | the recovery command only with the proxy on | 1 failed | `test_t303_2_…` |
| C7 | the offsite claim mounted read-write | 2 failed | both offsite-mount cases |

OB3's review measured one more on its copy: #304 simulated (offsite on by default, the mount left on the old
switch) turns `test_the_offsite_claim_is_mounted_exactly_when_the_cronjob_writes_one[default]` red, where the
reviewed draft's chart tests stayed green.

### 4.3 The proof

§7 was not written by hand. The design was implemented in a detached copy of origin/main `dd51b91f` (the reviewed
draft's blocks with OB3's corrected bodies applied, then this revision's changes); a generator cut each block's Old
text from `dd51b91f` and its New text from the implemented copy, at whole lines, with the fewest context lines that
make the Old text unique, and checked that each file's blocks, applied in order, give the implemented file byte for
byte: `21 blocks across 12 files reproduce the dev copy`. Then, on a fresh detached worktree of `dd51b91f`:

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_E2_recovery_mode.md <tree>
    21 blocks check out across 12 files
    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_E2_recovery_mode.md <tree> --apply

After `--apply` every changed and created file is identical (`cmp`) to the implemented copy. On that tree, with
`PYTHONPATH` at its `local-development` and the venv's Python 3.14.7:

| check | command | result |
|---|---|---|
| the new tests, before the blocks | the two new modules copied into a clean tree of `dd51b91f` | `51 failed, 5 passed` (§4.2) |
| the new tests, after | `pytest tests/test_recovery_mode.py tests/test_chart_recovery_mode.py -q -p no:cacheprovider` | `56 passed in 11.91s` |
| hermetic suite | `pytest tests/ -q -p no:cacheprovider --deselect tests/test_ui.py --deselect tests/test_live_smoke.py` | `6182 passed, 22 skipped, 655 deselected, 5 xfailed in 327.99s` |
| hermetic suite, this spec's commit alone | the same, in the spec's worktree before any block | `6159 passed, 25 skipped, 655 deselected, 5 xfailed in 305.94s` (the spec's branch, still at `5c03a9b1`'s code, with this revision of the spec and its index row); it carries none of the 56 new tests, and its count includes `test_docs_citations.py`'s checks of this spec's own anchored citations, three more of which skip because they name files the blocks create |
| browser suite | not run: no page, script or style of the application changes | — |
| chart | `helm lint` | `1 chart(s) linted, 0 chart(s) failed` |
| the default render across commits | `helm template` of `dd51b91f` and of the applied chart, the chart label normalised in both, by default and with `backup.offsite.enabled=true` | one line differs by default, the dashboard pod template's `checksum/config` (it hashes the ConfigMap, chart label included); with offsite on, also the bind Job's name (it hashes `.Chart.Version`). The report Deployment's pod template is unchanged: its annotation is `checksum/reporting`, a hash of `.Values.reporting` (`charts/group-sync-dashboard/templates/report-deployment.yaml#checksum/reporting`) |
| RBAC | `reports/2026-09-27_epic-c-walk/scripts/rbac_rules.py` on the render of `dd51b91f` against the applied chart, recovery off and on, by default and with offsite on | `rules: before 59, after 59`, `REMOVED 0`, `ADDED 0`, all four |
| markdown | `markdownlint-cli2` on the runbook, the CHANGELOG and the chart README | the same findings before and after, per file and rule (README MD004 ×6, MD040 ×4; CHANGELOG MD012 ×1; runbook MD004 ×3, MD040 ×3), all on main already; none new |
| Python 3.11 | `ast.parse(source, feature_version=(3, 11))` on the script (inside T303-12) | parses; CI's 3.11 job was not run here |
| the script under image 2.0.0 | §2.5, read-only on the lab (the first draft's script); and OB3's review, under the published amd64 image on a podman machine with qemu: run to a 3 s TTL with `-X importtime`, `/data` sealed (mode 000) around three files | `--help` exits 0 on the lab; under the image: exit 1 at the TTL, 101 modules imported, none of `sqlite3`, `_sqlite3`, `gsd`, `/data` mtimes unchanged, `/tmp` holding only `gsd-recovery.json`; a restart after the deadline exits 1 in 0.69 s. This revision adds only `math` and `/proc/sys/kernel/random/boot_id` to what the script touches; it was not re-run under the image |
| SIGTERM as PID 1 | §2.4, OB3's podman machine | 0.17 s native, 0.19 s under qemu, exit 0; a no-handler control waits the grace and exits 137 |

The cut and the proof are repeatable: the implemented copy, the generator and the mutation harness ran from this
spec's scratch directory and are not committed; so did the review's splice, render matrix and podman harnesses.

## 5. On the lab (the implementing pull request)

Not run in this phase: the lab is read-only here. The walk sets recovery mode the way an estate does, in a values
file rolled out through the lab's pipeline: `local-development/release-crc.sh --argocd <branch> --values <file>`
points the Application at the branch with that file as its only `valueFiles` entry and deploys the chart's default
image, the published 2.0.0, since this spec moves no `appVersion` (`local-development/release-crc.sh#apply_application()`;
the file replaces `environments/crc.yaml`, so each one is a copy of it plus the lines named below). The files are
committed under `reports/<date>_recovery-mode-303/` with the record:

1. **Before.** Record the UIDs of `group-sync-dashboard-data` and `group-sync-dashboard-report-artifacts` (today
   `f065b7a4-535c-4ef1-868c-58f5afee4953` and `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`) and the row counts of
   `membership_event`, `sync_event` and `binding_event` (runbook §4c's read-only query).
2. **On, under the image a rollback targets (T303-13).** Roll out `values-on.yaml`: `recovery.enabled: true`,
   `recovery.ttl: 2h` and `image.tag: 2.0.0` (a rollback's shape, set in the same change). `oc logs … -c dashboard`
   shows the four banner lines, not `ModuleNotFoundError`; `oc get pod` shows `1/2 Running`;
   `oc get endpoints group-sync-dashboard` lists no ready address; the Deployment reads Progressing, then Degraded
   at 600 s.
3. **Holds (T303-17).** Wait past 11 minutes (`initialDelaySeconds` 10 + 2 × 300 s of the old liveness probe). The
   `restartCount` is unchanged, and `oc exec … -c dashboard -- ls -l /proc/*/fd` shows no descriptor on
   `/data/gsd.db`, `-wal` or `-shm`. The pod still runs the values file's settings (self-heal reverted nothing).
4. **A restart keeps the TTL.** `oc exec … -c dashboard -- sh -c 'kill -TERM 1'` (the image has no `kill` binary, measured:
   `ls /usr/bin/kill` fails and `type kill` says `kill is a shell builtin`; the handler exits 0 and the kubelet restarts the container at once): the new banner says `kept from this pod's first start` with the same end instant.
5. **The TTL ends visibly.** Roll out `values-ttl3m.yaml` (the same with `recovery.ttl: 3m`: a new pod, a new TTL).
   After three minutes the log ends with the summary line, which names the values file and no command, and within the next few minutes `oc get pod` shows `CrashLoopBackOff` with the restart count
   rising and `oc describe pod` a back-off message; `oc logs --previous --tail=1` is the summary line.
6. **SIGTERM as PID 1 (T303-11).** Time `oc delete pod <recovery pod> --wait` from the command to the pod's
   removal: well under the 30 s grace period. On this lab PID 1 is qemu-user; the review measured 0.19 s under
   qemu on a podman machine of the same shape (§2.4), and the lab's stop time is what is recorded here.
7. **Off (T303-18).** Roll out `values-off.yaml` (`recovery.enabled: false`, `image.tag: 2.0.0` kept). The app
   starts on the same `/data/gsd.db`, the three row counts equal step 1's, the endpoints list the pod, and the
   UIDs are unchanged. Record the Application's operation phase when the rollout starts and the time to the app
   pod Ready (Orchestrator's notes, 13: a sync still waiting on step 5's rollout delays this one).
8. **RBAC.** The rule diff of the rendered chart, recovery off and on, against the merge base: REMOVED 0, ADDED 0
   (`reports/2026-09-27_epic-c-walk/scripts/rbac_rules.py`).

The offsite mount is not walked: the lab has no offsite CronJob, and #304's walk turns it on.

## 6. What an operator sees, and what it costs

- **Turning it on:** one change to the release's values file, rolled out through the release's pipeline. The
  dashboard stops (Recreate), a pod comes up `1/2 Running` (`0/1` with the proxy off) whose log says
  `RECOVERY MODE`, the app is not running, the data path, and when the TTL ends; every 30 minutes a line says how
  much is left. `oc exec` into it reaches `/data` (and `/offsite`, read-only, with an offsite `pvc` destination);
  no process holds `gsd.db`.
- **While it is on:** the route has no ready endpoint (what the router shows was not measured); a pipeline step
  that waits for the rollout reports it failed (`helm upgrade --wait` times out; Argo CD shows the Deployment
  Progressing, then Degraded); nothing is recorded; with reporting on, `GroupSyncDashboardReportSnapshotStale`
  (warning) fires after about 50 minutes.
- **At the TTL:** every process in the container stops, a restore still running included (so check the time left
  before one), `CrashLoopBackOff`, and a log that ends with what to change: a longer `recovery.ttl` in the values
  file to extend, `recovery.enabled: false` to leave. A pod
  replaced by an eviction or a drain starts a new TTL.
- **Turning it off:** when the values change is applied, the recovery pod stops at once and the app starts on
  whatever is in `/data/gsd.db`.
- **Cost:** one ConfigMap (11,300 bytes rendered, measured) and one Python process sleeping, only while on; nothing when off.
  No new permission. The chart's default render is unchanged.
- **Code:** the table below, from `git diff --numstat` on the applied copy (§4.3).

| file | added | removed |
|---|---|---|
| `charts/group-sync-dashboard/scripts/recovery_mode.py` (new) | 196 | 0 |
| `charts/group-sync-dashboard/templates/_helpers.tpl` | 24 | 0 |
| `charts/group-sync-dashboard/templates/deployment.yaml` | 87 | 3 |
| `charts/group-sync-dashboard/templates/recovery.yaml` (new) | 15 | 0 |
| `charts/group-sync-dashboard/values.yaml` | 39 | 0 |
| `charts/group-sync-dashboard/Chart.yaml` | 5 | 1 |
| `charts/group-sync-dashboard/README.md` | 31 | 0 |
| `docs/RUNBOOK_backup_restore.md` | 53 | 3 |
| `docs/CHANGELOG.md` | 18 | 0 |
| `local-development/tests/test_recovery_mode.py` (new) | 226 | 0 |
| `local-development/tests/test_chart_recovery_mode.py` (new) | 266 | 0 |
| `local-development/tests/test_values_defaults.py` | 1 | 0 |
| total | 961 | 7 |

## 7. Implementation blocks

Applied in this order. Block 1 creates the script; blocks 2 to 9 are the templates; 10 and 11 are `values.yaml` and
`Chart.yaml`; 12 to 18 are the documents; 19 to 21 are the tests. Inline code only in the documents' New text: a
fence inside a block would end the block.

### Block 1 — charts/group-sync-dashboard/scripts/recovery_mode.py: the recovery script

Standard library only; the banner, the countdown, the deadline kept in `$TMPDIR` and counted on the node's monotonic clock, what to change at the TTL (the release's values file), the SIGTERM handler (§3.5, §3.6).

<!-- block: charts/group-sync-dashboard/scripts/recovery_mode.py | create -->

```python
#!/usr/bin/env python3
"""Recovery mode (#303): the dashboard pod with its data volume mounted and the app stopped.

The chart runs this instead of uvicorn while `recovery.enabled` is true. It ships in a ConfigMap
(templates/recovery.yaml), not in the image, so it runs under any image with python3.14: the older
image a rollback targets has no recovery code of its own. Standard library only. It never imports
gsd or sqlite3 and opens nothing under the data directory, so no process holds gsd.db while an
operator restores it.

It prints what the pod is, then the time left every --report-every seconds, and exits 1 at the
TTL so the pod reads CrashLoopBackOff, saying how to extend recovery mode or leave it: a change to
the release's values file, rolled out through the release's deployment pipeline. As the container's
PID 1, its exit at the TTL also ends every process in the container, an `oc exec` restore included.

The deadline is kept in $TMPDIR (the pod's /tmp, an emptyDir), because the kubelet restarts an
exited container in the same pod at once and resets its back-off after ten minutes of running: a
TTL counted from each start would sleep another full TTL after every expiry. The emptyDir survives
a container restart and goes with the pod, so a new pod (a new recovery.ttl, a deleted or evicted
pod) starts a new TTL. The time left is measured on the node's monotonic clock, which a change of the
wall clock does not move and a container restart does not reset; after a node restart it cannot be
measured, so the TTL counts as reached. #302's restore wrapper reads the same file.

Exit status: 0 on SIGTERM, 1 at the TTL, 2 when the TTL or the deadline file cannot be used.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

#: The file under $TMPDIR (default /tmp) that keeps this pod's deadline across container restarts.
STATE_NAME = "gsd-recovery.json"
#: Generated once per boot of the node (random(4)); CLOCK_MONOTONIC counts from that boot (clock_gettime(2)).
BOOT_ID = Path("/proc/sys/kernel/random/boot_id")
#: Seconds between two "time left" lines.
REPORT_EVERY = 1800.0
#: The Go duration grammar of the chart's gsd.durationSeconds helper (templates/_helpers.tpl), so
#: the script accepts exactly what the render accepted. \u00b5 is the micro sign Go also accepts.
_DURATION = re.compile("(?:[0-9]+(?:\\.[0-9]+)?(?:ns|us|\u00b5s|ms|s|m|h))+")
_TOKEN = re.compile("([0-9]+(?:\\.[0-9]+)?)(ns|us|\u00b5s|ms|s|m|h)")
_UNIT = {"ns": 1e-9, "us": 1e-6, "\u00b5s": 1e-6, "ms": 1e-3, "s": 1.0, "m": 60.0, "h": 3600.0}
_IDLE = "the app is NOT running and no data is collected"


class _Stop(Exception):
    """SIGTERM arrived. Raised from the handler so a sleep ends at once."""


def _on_sigterm(signum: int, frame: object) -> None:
    # A handler of our own, not the default: as the container's PID 1 the process receives only
    # the signals it has a handler for (pid_namespaces(7)), and Python installs none for SIGTERM,
    # so without this the kubelet would wait out the whole grace period and then SIGKILL.
    raise _Stop


def ttl_seconds(text: str) -> float | None:
    """A Go duration as seconds (`2h`, `90m`, `1h30m`, `1.5s`), or None when the text is not one."""
    if not _DURATION.fullmatch(text):
        return None
    return sum(float(number) * _UNIT[unit] for number, unit in _TOKEN.findall(text))


def span(seconds: float) -> str:
    """Whole seconds as a compact Go duration (`2h`, `1h30m`, `45s`), valid as a recovery.ttl."""
    total = max(0, int(round(seconds)))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    text = (f"{hours}h" if hours else "") + (f"{minutes}m" if minutes else "") + (f"{secs}s" if secs else "")
    return text or "0s"


def instant(epoch: float) -> str:
    """ISO-8601 UTC to the second."""
    return datetime.fromtimestamp(epoch, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def say(message: str) -> None:
    print(f"{instant(time.time())} gsd-recovery {message}", flush=True)


def boot_id() -> str:
    """The node's boot ID; empty where there is none (a development machine that is not Linux)."""
    try:
        return BOOT_ID.read_text().strip()
    except OSError:
        return ""


def deadline(state: Path, ttl: float, ttl_text: str, wall: float, monotonic: float, boot: str) -> tuple[dict, bool]:
    """This pod's deadline record, and whether an earlier start in the pod wrote it.

    The first start writes it (to a temporary name, then renamed, so a kill mid-write leaves no
    half file); every later start in the same pod reads it back unchanged. A record that lacks a
    field is refused (KeyError, ValueError) rather than replaced, so a bad file never restarts the
    clock."""
    try:
        kept = json.loads(state.read_text())
        for key in ("started_epoch", "deadline_epoch", "deadline_monotonic"):
            if not math.isfinite(float(kept[key])):
                raise ValueError(f"{key} is not a finite number")
        str(kept["boot_id"])
        return kept, True
    except FileNotFoundError:
        pass
    record = {"ttl": ttl_text, "started": instant(wall), "started_epoch": wall,
              "deadline": instant(wall + ttl), "deadline_epoch": wall + ttl,
              "deadline_monotonic": monotonic + ttl, "boot_id": boot}
    partial = state.with_name(state.name + ".tmp")
    partial.write_text(json.dumps(record) + "\n")
    os.replace(partial, state)
    return record, False


def remaining(record: dict, ttl: float, monotonic: float, boot: str) -> float:
    """Seconds left, on the node's monotonic clock, never more than the TTL.

    The wall clock is not read: a step of it backwards would lengthen the TTL (review of the spec,
    Codex F1). CLOCK_MONOTONIC is system-wide and counts from the node's boot, so it runs on across
    container restarts; a different boot ID means the node restarted under the pod and the time
    left cannot be measured, which counts as reached."""
    if str(record["boot_id"]) != boot:
        return 0.0
    return min(float(record["deadline_monotonic"]) - monotonic, ttl)


def _expired(ttl_text: str, ttl: float, release: str, db: str, rebooted: bool) -> None:
    # The values file, rolled out through the release's own pipeline, is the one way recovery mode changes
    # (the operator, 2026-10-01): no Helm or Argo CD command line, which an estate's pipeline owns.
    longer = span(max(2 * ttl, 1.0))
    if rebooted:
        say("the node restarted since this pod's first start, so the time left cannot be measured; the TTL counts as reached")
    say(f"TTL {ttl_text} reached at {instant(time.time())}; exiting 1: the app is still NOT running and no data is collected")
    say(f"to extend: set a longer recovery.ttl (for example {longer}) in release {release}'s values file and roll it"
        f" out through its deployment pipeline; the new pod counts it from its start")
    say(f"to leave: set recovery.enabled: false in release {release}'s values file and roll it out; the app starts on {db}")
    say(f"TTL {ttl_text} reached; exiting 1. Extend with recovery.ttl, leave with recovery.enabled: false, in the"
        f" release's values file (lines above)")


def run(args: argparse.Namespace) -> int:
    ttl_text = os.environ.get("GSD_RECOVERY_MODE_TTL", "")
    ttl = ttl_seconds(ttl_text)
    if not ttl:
        say(f"GSD_RECOVERY_MODE_TTL {ttl_text!r} is not a positive Go duration such as 2h, 90m or 1h30m; exiting 2")
        return 2
    state = Path(os.environ.get("TMPDIR") or "/tmp") / STATE_NAME
    boot = boot_id()
    try:
        record, kept = deadline(state, ttl, ttl_text, time.time(), time.monotonic(), boot)
        left = remaining(record, ttl, time.monotonic(), boot)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        say(f"the deadline file {state} cannot be used ({type(exc).__name__}: {exc}), so the TTL could not be kept;"
            f" exiting 2. Delete the pod to start a new one with a new TTL")
        return 2
    db = os.environ.get("GSD_DB_PATH", "/data/gsd.db")
    say(f"RECOVERY MODE (GSD_RECOVERY_MODE={os.environ.get('GSD_RECOVERY_MODE', '')}, GSD_RECOVERY_MODE_TTL={ttl_text})")
    say(_IDLE)
    say(f"data path {db} (not opened by this process)")
    since = f" (kept from this pod's first start at {instant(float(record['started_epoch']))}; the container restarted)" if kept else ""
    say(f"TTL {ttl_text}: ends {instant(time.time() + max(left, 0.0))}, {span(left)} left{since}")
    say("check the time left before a restore: at the TTL this process exits and every process in the container"
        " stops with it")
    while True:
        left = remaining(record, ttl, time.monotonic(), boot)
        if left <= 0:
            _expired(ttl_text, ttl, args.release, db, str(record["boot_id"]) != boot)
            return 1
        time.sleep(min(left, args.report_every))
        left = remaining(record, ttl, time.monotonic(), boot)
        if left > 0:
            say(f"{span(left)} left; {_IDLE}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recovery mode (#303): hold the pod with the app stopped until the TTL.")
    parser.add_argument("--release", default="group-sync-dashboard", help="the release whose values file the TTL lines name")
    parser.add_argument("--report-every", type=float, default=REPORT_EVERY, help="seconds between two 'time left' lines")
    args = parser.parse_args(argv)
    try:
        signal.signal(signal.SIGTERM, _on_sigterm)
        return run(args)
    except _Stop:
        say("SIGTERM: stopping (exit 0); the app was not running")
        return 0


if __name__ == "__main__":
    sys.exit(main())
```

### Block 2 — charts/group-sync-dashboard/templates/_helpers.tpl: the two recovery helpers

`gsd.recoveryEnabled` (a word, nil-safe) and `gsd.recoveryTtl` (as typed, `2h` when absent), after `gsd.durationSeconds` (§3.1).

<!-- block: charts/group-sync-dashboard/templates/_helpers.tpl | edit -->

Old text:

```yaml
{{- if eq (floor $total) $total -}}{{ int64 $total }}{{- else -}}{{ $total }}{{- end -}}
{{- end -}}
{{- end -}}

```

New text:

```yaml
{{- if eq (floor $total) $total -}}{{ int64 $total }}{{- else -}}{{ $total }}{{- end -}}
{{- end -}}
{{- end -}}

# Recovery mode (#303). Both reads are nil-safe: `helm upgrade --reuse-values` onto this chart from
# one without the `recovery` block renders with the OLD chart's values (Helm's reuseValues sets
# chart.Values to them), so `.Values.recovery` is absent there and a bare field access would fail
# the default render. The switch is read as a word and anything but true/false is refused: a quoted
# "false" from --set-string would otherwise be a non-empty string, which a template `if` treats as
# true, and turning recovery on stops the dashboard.
{{- define "gsd.recoveryEnabled" -}}
{{- $v := toString ((.Values.recovery | default dict).enabled) -}}
{{- if eq $v "true" -}}
true
{{- else if has $v (list "false" "" "<nil>") -}}
false
{{- else -}}
{{- fail (printf "recovery.enabled %q is not true or false. It turns recovery mode on (the dashboard stops and the pod waits for a restore) or off." $v) -}}
{{- end -}}
{{- end -}}

# The recovery TTL as typed, `2h` when the key is absent. Not `default`: Helm's default treats a
# numeric 0 as empty, and `ttl: 0` must be refused by name, not become two hours.
{{- define "gsd.recoveryTtl" -}}
{{- $r := .Values.recovery | default dict -}}
{{- if hasKey $r "ttl" -}}{{- toString $r.ttl -}}{{- else -}}2h{{- end -}}
{{- end -}}

```

### Block 3 — charts/group-sync-dashboard/templates/deployment.yaml: the switch and the refusals

`$recovery` and `$offsiteClaim`, computed once beside the chart's other guards; the four refusals, `replicaCount` compared as text (§3.7, §3.8).

<!-- block: charts/group-sync-dashboard/templates/deployment.yaml | edit -->

Old text:

```yaml
{{- include "gsd.reportingGuards" . }}
{{- if .Values.oauthProxy.enabled }}
```

New text:

```yaml
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
{{- fail (printf "recovery.enabled=true requires replicaCount: 1 (it is %v). Recovery mode is ONE pod holding the data volume with the writer stopped: at 0 there is no pod to restore from, and a second recovery pod is a second shell that can write the same file on a ReadWriteMany volume, or a pod that stays Pending on ReadWriteOnce and ReadWriteOncePod." .Values.replicaCount) }}
{{- end }}
{{- if not .Values.persistence.enabled }}
{{- fail "recovery.enabled=true requires persistence.enabled=true. With an emptyDir there is no database to restore onto, and anything copied into it is wiped when the pod goes." }}
{{- end }}
{{- $ttl := include "gsd.recoveryTtl" . }}
{{- $ttlSeconds := include "gsd.durationSeconds" $ttl }}
{{- if eq $ttlSeconds "-1" }}
{{- fail (printf "recovery.ttl %q is not a duration. Use a Go duration such as 2h (the default), 90m or 1h30m; a bare number has no unit and is refused. The TTL is what ends a forgotten recovery pod." $ttl) }}
{{- end }}
{{- if eq $ttlSeconds "0" }}
{{- fail (printf "recovery.ttl %q is zero: the recovery pod would exit at once and crash-loop. Use a positive Go duration such as 2h (the default)." $ttl) }}
{{- end }}
{{- /* The offsite claim, read-only, so #302's restore can list the offsite copies: the same switch
and the same claim the CronJob renders with (backup-offsite.yaml). */}}
{{- if and .Values.backup.offsite.enabled (eq .Values.backup.offsite.destination.type "pvc") }}
{{- $offsiteClaim = .Values.backup.offsite.destination.pvc.existingClaim | default (printf "%s-backup-offsite" (include "gsd.fullname" .)) }}
{{- end }}
{{- end }}
{{- if .Values.oauthProxy.enabled }}
```

### Block 4 — charts/group-sync-dashboard/templates/deployment.yaml: the command

The recovery script before the proxy's uvicorn branch, so it replaces the image's `CMD` too (§3.2).

<!-- block: charts/group-sync-dashboard/templates/deployment.yaml | edit -->

Old text:

```yaml
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          {{- if .Values.oauthProxy.enabled }}
          # Bind loopback only. Otherwise 8080 stays reachable pod-network-wide and anything
```

New text:

```yaml
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          {{- if $recovery }}
          # RECOVERY MODE (#303): the chart's stdlib script instead of uvicorn, whether or not the
          # proxy is on (the image's CMD is uvicorn too). It ships in a ConfigMap, not the image, so
          # it runs under the older image a rollback targets; it never opens the database.
          command:
            - python3.14
            - /scripts/recovery_mode.py
            - --release
            - {{ .Release.Name | quote }}
          {{- else if .Values.oauthProxy.enabled }}
          # Bind loopback only. Otherwise 8080 stays reachable pod-network-wide and anything
```

### Block 5 — charts/group-sync-dashboard/templates/deployment.yaml: the environment

`GSD_RECOVERY_MODE` and `GSD_RECOVERY_MODE_TTL` after the existing variables (§3.3).

<!-- block: charts/group-sync-dashboard/templates/deployment.yaml | edit -->

Old text:

```yaml
              value: /etc/curl
          securityContext: {{- toYaml .Values.securityContext | nindent 12 }}
```

New text:

```yaml
              value: /etc/curl
            {{- if $recovery }}
            # Read by the recovery script, and by #302's restore wrapper to know it is in recovery mode.
            - name: GSD_RECOVERY_MODE
              value: "true"
            - name: GSD_RECOVERY_MODE_TTL
              value: {{ include "gsd.recoveryTtl" . | quote }}
            {{- end }}
          securityContext: {{- toYaml .Values.securityContext | nindent 12 }}
```

### Block 6 — charts/group-sync-dashboard/templates/deployment.yaml: the mounts, and no liveness probe

The script at `/scripts`, the offsite claim at `/offsite`, read-only; the liveness probe skipped in recovery mode (§3.4, §3.8).

<!-- block: charts/group-sync-dashboard/templates/deployment.yaml | edit -->

Old text:

```yaml
            {{- end }}
          {{- if .Values.probes.liveness.enabled }}
          livenessProbe:
```

New text:

```yaml
            {{- end }}
            {{- if $recovery }}
            - name: recovery-script
              mountPath: /scripts
              readOnly: true
            {{- if $offsiteClaim }}
            # Read-only: the copies are listed and read from here, never written.
            - name: offsite
              mountPath: /offsite
              readOnly: true
            {{- end }}
            {{- end }}
          {{- /* No liveness probe in recovery mode: nothing serves /healthz, and a kill in the middle
          of a restore is the failure recovery mode exists to prevent. */}}
          {{- if and .Values.probes.liveness.enabled (not $recovery) }}
          livenessProbe:
```

### Block 7 — charts/group-sync-dashboard/templates/deployment.yaml: the readiness probe that cannot pass

Rendered whatever `probes.readiness.enabled` says (§3.4).

<!-- block: charts/group-sync-dashboard/templates/deployment.yaml | edit -->

Old text:

```yaml
          {{- end }}
          {{- if .Values.probes.readiness.enabled }}
          readinessProbe:
```

New text:

```yaml
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
```

### Block 8 — charts/group-sync-dashboard/templates/deployment.yaml: the volumes

The script's ConfigMap (mode 0444) and the offsite claim, read-only (§3.2, §3.8).

<!-- block: charts/group-sync-dashboard/templates/deployment.yaml | edit -->

Old text:

```yaml
            name: {{ include "gsd.fullname" . }}-curlrc
        {{- if .Values.trustedCA.injected.enabled }}
```

New text:

```yaml
            name: {{ include "gsd.fullname" . }}-curlrc
        {{- if $recovery }}
        - name: recovery-script
          configMap:
            name: {{ include "gsd.fullname" . }}-recovery
            defaultMode: 292   # 0444: read by any UID OpenShift assigns; nothing writes it
        {{- with $offsiteClaim }}
        - name: offsite
          persistentVolumeClaim:
            claimName: {{ . }}
            readOnly: true
        {{- end }}
        {{- end }}
        {{- if .Values.trustedCA.injected.enabled }}
```

### Block 9 — charts/group-sync-dashboard/templates/recovery.yaml: the script's ConfigMap

Rendered only while recovery is on, so the default render has no new object (§3.2, §3.12).

<!-- block: charts/group-sync-dashboard/templates/recovery.yaml | create -->

```yaml
{{- if eq (include "gsd.recoveryEnabled" .) "true" }}
# Recovery mode's script (#303), verbatim from scripts/recovery_mode.py; a test holds the two
# identical. Rendered only while recovery.enabled is true, so the default render has no extra object.
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "gsd.fullname" . }}-recovery
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "gsd.labels" . | nindent 4 }}
    app.kubernetes.io/component: recovery
data:
  recovery_mode.py: |
{{ .Files.Get "scripts/recovery_mode.py" | indent 4 }}
{{- end }}
```

### Block 10 — charts/group-sync-dashboard/values.yaml: the values and their comment

`recovery.enabled: false`, `recovery.ttl: 2h`, after `probes` (§3.1, §3.9, §3.10).

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->

Old text:

```yaml
    timeoutSeconds: 5
    failureThreshold: 3

# ---------------------------------------------------------------------------
```

New text:

```yaml
    timeoutSeconds: 5
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
# `oc set env` or an edit of the Deployment: a GitOps tool such as Argo CD (selfHeal) reverts a hand
# edit, and an environment variable alone would leave the liveness probe to kill the pod in the
# middle of a restore.
#
# While it is on the pod has no liveness probe, and a readiness probe that cannot pass keeps it
# out of the Service: READY reads 1/2 (the oauth-proxy sidecar is ready, the dashboard is not; 0/1
# with the proxy off), the route has no ready endpoint, and the Deployment never reports available,
# so a pipeline step that waits for the rollout reports it failed. When backup.offsite uses the pvc
# destination, its claim is mounted read-only at /offsite, so the offsite copies can be listed and read.
#
# NOTHING IS RECORDED WHILE IT IS ON, and no rule says recovery mode. GroupSyncDashboardNotPolling
# does not fire: its gauge comes from the stopped process, and a missing series returns nothing.
# With reporting on, GroupSyncDashboardReportSnapshotStale (warning) fires once the report
# service's newest copy is older than four snapshot intervals, for for.reportSnapshot (about 50
# minutes at the defaults). The TTL is the bound: a Go duration (2h, 90m, 1h30m), counted from the
# pod's first start and kept in its /tmp across container restarts; a new pod (a new recovery.ttl,
# a deleted or evicted pod) starts a new TTL. At the TTL the script exits 1 and every process in the
# container stops with it, an `oc exec` restore still running included; the pod reads
# CrashLoopBackOff, and the log says how to extend it (a longer recovery.ttl in the values file) or
# leave it. Refused at render: replicaCount other than 1, persistence.enabled=false, and a TTL that
# is not a positive duration.
#
# Stays false by default under the 0.14.0 rule: turning it on stops the dashboard.
recovery:
  enabled: false
  ttl: 2h

# ---------------------------------------------------------------------------
```

### Block 11 — charts/group-sync-dashboard/Chart.yaml: the chart MINOR and its history line

§3.11. `appVersion` unchanged.

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->

Old text:

```yaml
# are the last poll's, not Refresh's (Epic D composition review, K5).
version: 0.59.25
# 0.8.0 (2026-09-03). A Users tab — every user with a synced membership, filtered as you type on
```

New text:

```yaml
# are the last poll's, not Refresh's (Epic D composition review, K5).
# CHART 0.60.0 (2026-10-01), MINOR: recovery.enabled and recovery.ttl (#303, SPEC_E2). The dashboard
# container runs the chart's recovery script (a ConfigMap rendered only while it is on) instead of
# uvicorn, with no liveness probe and a readiness probe that cannot pass. The default render is
# unchanged apart from this version and what is computed from it; no RBAC change; appVersion unchanged.
version: 0.60.0
# 0.8.0 (2026-09-03). A Users tab — every user with a synced membership, filtered as you type on
```

### Block 12 — charts/group-sync-dashboard/README.md: the chart README: Recovery mode

A subsection after the Workload table: the two rows, how to set them, what alerts (§3.9, §3.10).

<!-- block: charts/group-sync-dashboard/README.md | edit -->

Old text:

```text
| `priorityClassName`, `reporting.priorityClassName` | `""` | a PriorityClass name for the dashboard / report pod, rendered only when set. A PDB does not stop preemption; set these when a workload must outrank profile-collection crons on a saturated node (#97) |

```

New text:

```text
| `priorityClassName`, `reporting.priorityClassName` | `""` | a PriorityClass name for the dashboard / report pod, rendered only when set. A PDB does not stop preemption; set these when a workload must outrank profile-collection crons on a saturated node (#97) |

### Recovery mode — `recovery`

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
pipeline step that waits for the rollout reports it failed.

**Nothing is recorded while it is on.** No rule says recovery mode: `GroupSyncDashboardNotPolling` does not
fire, because its gauge comes from the stopped process and a missing series returns nothing. With
`reporting.enabled`, `GroupSyncDashboardReportSnapshotStale` (warning) fires once the report service's
newest copy is older than four snapshot intervals, for `for.reportSnapshot` (about 50 minutes at the
defaults). The TTL is the bound. The procedure is the runbook's
[§4](../../docs/RUNBOOK_backup_restore.md#4-restore).

```

### Block 13 — charts/group-sync-dashboard/README.md: the chart README: Upgrading

A restore before or after an upgrade uses recovery mode, set in the values file with a rollback's `image.tag` (§2.7, §3.9).

<!-- block: charts/group-sync-dashboard/README.md | edit -->

Old text:

```text

## Uninstall
```

New text:

```text

**To restore the database, before or after an upgrade, use [recovery mode](#recovery-mode--recovery).**
For a rollback, set the older `image.tag` and `recovery.enabled: true` in the same change to the
values file, restore, then set `recovery.enabled: false` in the next one, keeping the older tag: the
older image starts the app. The chart reads `recovery` so that its absence means off, so a
`--reuse-values` upgrade from an older chart, which renders with that chart's defaults, still renders.

## Uninstall
```

### Block 14 — docs/RUNBOOK_backup_restore.md: the runbook: §4, recovery mode as the primary path

The five steps through the release's values file, the time left checked before a restore, what alerts, one labelled development line; the `oc scale` path kept as the fallback (§3.9).

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
file corrupt rather than error (`gsd/store.py#Store.__init__`).

```sh
oc scale -n $NS deploy/$REL --replicas=0
```

New text:

```text
file corrupt rather than error (`gsd/store.py#Store.__init__`).

**Recovery mode is the primary path (chart 0.60.0 and later, #303).** The dashboard pod keeps its spec and
its data volume but runs the chart's recovery script instead of the app
(`charts/group-sync-dashboard/scripts/recovery_mode.py`), so nothing opens `gsd.db`, and it stays up until
`recovery.ttl` (2h by default): a dropped `oc` session does not end it. It is a value like any other: set it
in this release's values file and roll it out through the release's deployment pipeline. Never with
`oc set env` or an edit of the Deployment: a GitOps tool such as Argo CD (selfHeal) reverts a hand edit.

1. **Turn it on, with the image you will restore under.** In the release's values file set
   `recovery.enabled: true` and `recovery.ttl` (for example `2h`, longer than the restore needs), and roll it
   out. For a rollback, set the older `image.tag` in the same change, so the restore runs under the image
   that will open the file.
2. **Wait for the recovery pod.** `oc get pods -n $NS -l app=$REL` shows `1/2` ready (`0/1` with the proxy
   off) and `Running`: the dashboard container is not ready, so the Service sends it nothing.
   `oc logs -n $NS deploy/$REL -c dashboard` starts with `RECOVERY MODE`, `the app is NOT running and no data
   is collected` and the TTL's end. With `backup.offsite` on its `pvc` destination, the offsite claim is at
   `/offsite`, read-only. The Deployment never reports available, so a pipeline step that waits for the
   rollout reports it failed; that is expected.
3. **Restore** with §4a or §4b, running their commands with `oc exec -n $NS deploy/$REL -c dashboard -- sh -c '…'`
   instead of `oc debug` or a helper pod. **Check the time left first** (the last `left` line of `oc logs`):
   at the TTL the script exits and every process in the container stops with it, a restore still running
   included, which leaves `gsd.db` half written. If the restore may not finish in time, extend first.
4. **More time?** At the TTL the script exits 1, the pod reads `CrashLoopBackOff`, and the log ends with how to
   extend or leave. Set a longer `recovery.ttl` (for example `4h`) in the values file and roll it out: the new
   pod counts it from its start. `oc delete pod` starts the same TTL again in a new pod, with no values
   change. Either replaces the pod and ends any `oc exec` session in it; so does an eviction or a node drain,
   whose new pod also starts a new TTL. The time left is counted on the node's monotonic clock, so setting
   the wall clock back does not lengthen it; if the node restarts under the pod, the TTL counts as reached.
5. **Turn it off**, and verify with §4c: set `recovery.enabled: false` in the values file (keep a rollback's
   older `image.tag`) and roll it out. When the change is applied the recovery pod stops at once and the app
   starts on the restored file.

Nothing is recorded while recovery mode is on, and no rule says so: `GroupSyncDashboardNotPolling` reads a
gauge the stopped process no longer emits, so it returns nothing. With reporting on,
`GroupSyncDashboardReportSnapshotStale` (warning) fires after about 50 minutes, because the report service's
newest copy stops advancing. The TTL is the bound.

**Development and troubleshooting only:** with plain Helm and no pipeline, the same change is
`helm upgrade $REL <chart> -n $NS -f <values-file>`, with the chart reference and version the release already
runs (`helm list -n $NS`) and the release's complete values file, now carrying `recovery`.

**Without recovery mode** (the fallback, and any chart before 0.60.0), scale the writer to zero and use the
`oc debug` pod of §4a or the helper pod of §4b:

```sh
oc scale -n $NS deploy/$REL --replicas=0
```

### Block 15 — docs/RUNBOOK_backup_restore.md: the runbook: §4a in recovery mode

The same body through `oc exec` into the recovery pod.

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text

A helper pod with the data claim, from the Deployment's own template:

```

New text:

```text

In recovery mode the dashboard pod already has the data claim: run the `sh -c '…'` body below with
`oc exec -n $NS deploy/$REL -c dashboard --` in place of `oc debug -n $NS deploy/$REL -c dashboard --`.
Otherwise, a helper pod with the data claim, from the Deployment's own template:

```

### Block 16 — docs/RUNBOOK_backup_restore.md: the runbook: §4b in recovery mode

The offsite claim is already mounted at `/offsite`.

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text

A one-off pod mounting both claims (the `debug` pod has only the data claim). There is no
`sleep`; Python idles instead:

```

New text:

```text

In recovery mode the dashboard pod mounts the offsite claim read-only at `/offsite` (with
`backup.offsite` on its `pvc` destination): skip the helper pod and run the `oc exec` body below against
`deploy/$REL -c dashboard`. Otherwise, a one-off pod mounting both claims (the `debug` pod has only the
data claim). There is no `sleep`; Python idles instead:

```

### Block 17 — docs/RUNBOOK_backup_restore.md: the runbook: §4c in recovery mode

Turning it off replaces the `oc scale`.

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
### 4c. Bring it back and verify

```

New text:

```text
### 4c. Bring it back and verify

In recovery mode, turn it off (§4, step 5) instead of the `oc scale` below: the app starts on the restored
file. The rest of this section is the same.

```

### Block 18 — docs/CHANGELOG.md: the CHANGELOG entry

Under Unreleased, naming chart 0.60.0 (§3.11).

<!-- block: docs/CHANGELOG.md | edit -->

Old text:

```text

- **The runbook says which card rows are the last poll's (Epic D composition review, K5).** Refresh stores nothing
```

New text:

```text

- **Recovery mode: the dashboard pod with its data volume mounted and the app stopped, for a restore (#303,
  Epic E #385, `docs/specs/SPEC_E2_recovery_mode.md`; chart 0.60.0, no application change).**
  `recovery.enabled=true` runs the chart's recovery script (`charts/group-sync-dashboard/scripts/recovery_mode.py`,
  shipped in a ConfigMap rendered only while it is on) instead of uvicorn, with or without the proxy, on the
  same pod spec and `/data` volume, with `GSD_RECOVERY_MODE=true` and `GSD_RECOVERY_MODE_TTL`. The script is
  standard library only, so it runs under the older image a rollback targets; it never opens the database.
  The pod has no liveness probe and a readiness probe that cannot pass, so it stays out of the Service; with
  `backup.offsite` on its `pvc` destination the offsite claim is mounted read-only at `/offsite`.
  `recovery.ttl` (2h) is counted from the pod's first start and kept in its `/tmp` across container
  restarts; at the TTL the script exits 1, every process in the container stops with it, the pod reads
  `CrashLoopBackOff`, and its log says how to extend or leave recovery mode. The render refuses `replicaCount`
  other than 1, `persistence.enabled=false` and a TTL that is not a positive duration. Set it in the
  release's values file and roll it out through the deployment pipeline, never with `oc set env`. No rule
  says recovery mode: `GroupSyncDashboardNotPolling` does not fire, and with reporting on
  `GroupSyncDashboardReportSnapshotStale` fires after about 50 minutes; the TTL is the bound. The default
  render is unchanged apart from the chart version and what is computed from it (the pod's `checksum/config`,
  the offsite bind Job's name); no RBAC change. The runbook's §4 uses recovery mode as the primary path and
  keeps `oc debug` as the fallback.
- **The runbook says which card rows are the last poll's (Epic D composition review, K5).** Refresh stores nothing
```

### Block 19 — local-development/tests/test_recovery_mode.py: the script's tests

§4.1: T303-8 to T303-12 and the restart, clock, deadline-file, extension and grammar tests.

<!-- block: local-development/tests/test_recovery_mode.py | create -->

```python
"""Recovery mode's script (#303), run as the pod runs it: a separate Python process.

The script is `charts/group-sync-dashboard/scripts/recovery_mode.py`, shipped in a ConfigMap so it
runs under the older image a rollback targets. These tests hold what the issue asks of it: it never
imports the store or sqlite3 and never touches the data directory; it says what the pod is; it ends
at the TTL saying how to extend it, through the release's values file and nothing else; it stops on
SIGTERM at once; and the TTL survives a container restart, which the kubelet performs at once after
an exit.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import pathlib
import re
import signal
import subprocess
import sys
import time
from datetime import datetime

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "charts" / "group-sync-dashboard" / "scripts" / "recovery_mode.py"
STAMP = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ gsd-recovery ")
IDLE = "the app is NOT running and no data is collected"
#: What the log at the TTL must never print (the operator, 2026-10-01): the values file through the release's
#: deployment pipeline is the one way to change recovery mode, so no Helm or Argo CD command line.
NOT_IN_THE_LOG = ("helm upgrade", "--set", "--reset-then-reuse-values", "--reuse-values", "argocd",
                  "applications.argoproj.io", "oc patch", "oc delete", "parameters")


def _module():
    spec = importlib.util.spec_from_file_location("recovery_mode", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _env(tmp: pathlib.Path, ttl: str, data: pathlib.Path | None = None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GSD_")}
    env.update(TMPDIR=str(tmp), GSD_RECOVERY_MODE="true", GSD_RECOVERY_MODE_TTL=ttl, POD_NAME="gsd-recovery-test",
               GSD_DB_PATH=str((data or tmp / "data") / "gsd.db"))
    return env


def _run(env: dict[str, str], *args: str, timeout: float = 30) -> tuple[subprocess.CompletedProcess, float]:
    started = time.monotonic()
    done = subprocess.run([sys.executable, *args, str(SCRIPT), "--release", "rel",
                           "--report-every", "0.5"], env=env, capture_output=True, text=True, timeout=timeout)
    return done, time.monotonic() - started


def _start(env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, str(SCRIPT), "--release", "rel"], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _banner(proc: subprocess.Popen) -> list[str]:
    return [proc.stdout.readline().rstrip("\n") for _ in range(4)]


def test_t303_8_it_imports_neither_the_store_nor_sqlite3_and_touches_nothing_in_the_data_directory(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    for name in ("gsd.db", "gsd.db-wal", "gsd.db-shm"):
        (data / name).write_bytes(b"live database bytes")
    before = {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in data.iterdir()}
    sealed = os.geteuid() != 0                       # root ignores the mode; the listing still holds
    if sealed:
        data.chmod(0o000)                            # any open or stat under it would now fail
    try:
        done, _ = _run(_env(tmp_path, "1s", data), "-X", "importtime")
    finally:
        data.chmod(0o755)
    imported = {line.rsplit("|", 1)[1].strip() for line in done.stderr.splitlines() if line.startswith("import time:")}
    assert imported, done.stderr                     # -X importtime ran, so the absence below means something
    assert not {"sqlite3", "_sqlite3", "gsd", "gsd.store"} & imported, sorted(imported)
    assert "Traceback" not in done.stderr and done.returncode == 1, (done.returncode, done.stderr[-2000:])
    assert "TTL 1s reached" in done.stdout
    assert {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in data.iterdir()} == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["data", "gsd-recovery.json"]


def test_t303_9_the_log_says_what_the_pod_is_then_counts_down_in_utc(tmp_path):
    done, _ = _run(_env(tmp_path, "3s"))
    lines = done.stdout.splitlines()
    stamped = [line for line in lines if not line.startswith("  ")]
    assert all(STAMP.match(line) for line in stamped), lines
    banner = "\n".join(lines[:4])
    for words in ("RECOVERY MODE", "GSD_RECOVERY_MODE=true", "GSD_RECOVERY_MODE_TTL=3s", IDLE,
                  f"data path {tmp_path / 'data' / 'gsd.db'} (not opened by this process)", "TTL 3s: ends ", "3s left"):
        assert words in banner, (words, banner)
    assert "check the time left before a restore" in lines[4] and "every process in the container stops" in lines[4]
    countdown = [line for line in lines[5:] if line.endswith(f"left; {IDLE}")]
    assert len(countdown) >= 2, lines


def test_t303_10_at_the_ttl_it_exits_1_and_says_how_to_extend_or_leave_through_the_values_file(tmp_path):
    done, took = _run(_env(tmp_path, "1s"))
    assert done.returncode == 1 and took < 1 + 1.5, (done.returncode, took)
    out = done.stdout
    assert "TTL 1s reached at " in out
    assert "set a longer recovery.ttl (for example 2s) in release rel's values file and roll it out" in out
    assert "set recovery.enabled: false in release rel's values file and roll it out" in out
    assert not [word for word in NOT_IN_THE_LOG if word in out.lower()], out
    last = out.splitlines()[-1]
    assert STAMP.match(last) and "TTL 1s reached" in last and "recovery.ttl" in last and "recovery.enabled: false" in last


def test_t303_11_sigterm_stops_it_at_once_through_its_own_handler(tmp_path):
    proc = _start(_env(tmp_path, "1h"))
    try:
        assert "TTL 1h: ends " in _banner(proc)[3]
        sent = time.monotonic()
        proc.send_signal(signal.SIGTERM)
        out, _ = proc.communicate(timeout=5)
        took = time.monotonic() - sent
    finally:
        proc.kill()
    # Exit 0 with the line, not -15: the default action would also end a child at once, so only the
    # handler's own exit proves the handler is installed, which is what a namespace's PID 1 needs.
    assert proc.returncode == 0 and took < 1.0, (proc.returncode, took)
    assert "SIGTERM: stopping (exit 0)" in out.splitlines()[-1]


def test_t303_12_every_import_is_from_the_standard_library():
    tree = ast.parse(SCRIPT.read_text(), feature_version=(3, 11))
    roots = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    roots |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert roots and roots <= set(sys.stdlib_module_names) | {"__future__"}, sorted(roots - set(sys.stdlib_module_names))
    assert not {"gsd", "sqlite3"} & roots


def test_the_ttl_survives_a_container_restart_and_an_expired_one_exits_at_once(tmp_path):
    """The kubelet restarts an exited container in the same pod at once and resets its back-off after
    ten minutes of running, so a TTL counted from each start would never end. The pod's /tmp (an
    emptyDir) outlives the container: the deadline kept there holds across restarts, and after it
    every start exits 1 at once, which is what keeps the pod in CrashLoopBackOff."""
    env = _env(tmp_path, "2s")
    first = _start(env)
    try:
        banner = _banner(first)
        first.send_signal(signal.SIGTERM)
        first.communicate(timeout=5)
    finally:
        first.kill()
    state = json.loads((tmp_path / "gsd-recovery.json").read_text())
    assert f"ends {state['deadline']}," in banner[3] and state["ttl"] == "2s"
    second = _start(env)                                    # a restarted container, the same pod's /tmp
    try:
        again = _banner(second)
    finally:
        second.kill()
        second.communicate()
    ends_again = datetime.fromisoformat(re.search(r"ends (\S+),", again[3]).group(1)).timestamp()
    assert abs(ends_again - state["deadline_epoch"]) <= 1.0, (again, state)
    assert f"kept from this pod's first start at {state['started']}" in again[3], again
    time.sleep(max(0.0, state["deadline_epoch"] - time.time()) + 0.2)
    third, took = _run(env)
    assert third.returncode == 1 and took < 1.0, (third.returncode, took)
    assert "0s left (kept from this pod's first start" in third.stdout and "TTL 2s reached" in third.stdout.splitlines()[-1]


def _record(tmp_path: pathlib.Path, **fields) -> None:
    """A deadline record as the script writes it, on this machine's clocks, with `fields` replaced."""
    module = _module()
    now, mono = time.time(), time.monotonic()
    record = {"ttl": "1h", "started": module.instant(now), "started_epoch": now, "deadline": module.instant(now + 3600),
              "deadline_epoch": now + 3600, "deadline_monotonic": mono + 3600, "boot_id": module.boot_id()}
    record.update(fields)
    (tmp_path / "gsd-recovery.json").write_text(json.dumps(record))


def test_a_backward_wall_clock_step_cannot_lengthen_the_ttl(tmp_path):
    """Codex F1: the time left came from the wall clock, so setting it back gave the pod more time. It now
    comes from the node's monotonic clock: a record whose wall-clock deadline is an hour away but whose
    monotonic deadline has passed is expired at once, and the arithmetic never returns more than the TTL."""
    module = _module()
    record, kept = module.deadline(tmp_path / "state.json", 60.0, "1m", wall=1000.0, monotonic=5000.0, boot="b")
    assert not kept and module.remaining(record, 60.0, 5010.0, "b") == 50.0    # 10 s on: 50 s left, whatever the wall says
    assert module.remaining({**record, "deadline_monotonic": 9999.0}, 60.0, 5010.0, "b") == 60.0
    _record(tmp_path, deadline_monotonic=time.monotonic() - 1)
    done, took = _run(_env(tmp_path, "1h"))
    assert done.returncode == 1 and took < 1.5 and "TTL 1h reached" in done.stdout.splitlines()[-1], done.stdout


def test_a_node_restart_under_the_pod_counts_as_the_ttl_reached(tmp_path):
    _record(tmp_path, boot_id="a-boot-that-is-not-this-one")
    done, took = _run(_env(tmp_path, "1h"))
    assert done.returncode == 1 and took < 1.5, (done.returncode, took)
    assert "the node restarted since this pod's first start" in done.stdout


def test_the_suggested_ttl_is_a_positive_duration_for_a_subsecond_ttl(tmp_path):
    """Codex: a 250ms TTL suggested `0s`, which the chart refuses."""
    done, _ = _run(_env(tmp_path, "250ms"))
    assert done.returncode == 1 and "set a longer recovery.ttl (for example 1s)" in done.stdout


@pytest.mark.parametrize("ttl", ["", "abc", "0s", "-5m", "7200"])
def test_a_ttl_that_is_not_a_positive_duration_exits_2(tmp_path, ttl):
    done, _ = _run(_env(tmp_path, ttl))
    assert done.returncode == 2 and "is not a positive Go duration" in done.stdout
    assert not (tmp_path / "gsd-recovery.json").exists()


@pytest.mark.parametrize("bad", ["{not json", json.dumps({"deadline_epoch": 1.0, "started_epoch": 1.0, "boot_id": ""}),
                                 json.dumps({"deadline_epoch": 1.0, "started_epoch": 1.0, "deadline_monotonic": "NaN",
                                             "boot_id": ""})], ids=["not-json", "no-monotonic-deadline", "nan"])
def test_a_deadline_file_that_cannot_be_read_exits_2_rather_than_restart_the_clock(tmp_path, bad):
    (tmp_path / "gsd-recovery.json").write_text(bad)
    done, _ = _run(_env(tmp_path, "1h"))
    assert done.returncode == 2 and "cannot be used" in done.stdout and "Delete the pod" in done.stdout
    assert (tmp_path / "gsd-recovery.json").read_text() == bad


def test_the_duration_grammar_and_the_printed_spans():
    module = _module()
    assert [module.ttl_seconds(t) for t in ("2h", "90m", "1h30m", "1.5s", "250ms")] == [7200, 5400, 5400, 1.5, 0.25]
    assert [module.ttl_seconds(t) for t in ("", "0", "abc", "-5m", "7200", "2H", "1 h")] == [None] * 7
    assert module.ttl_seconds("0s") == 0
    assert [module.span(s) for s in (7200, 5400, 5399.6, 59, 0.4)] == ["2h", "1h30m", "1h30m", "59s", "0s"]
```

### Block 20 — local-development/tests/test_chart_recovery_mode.py: the chart's tests

§4.1: T303-1 to T303-7, T303-14 to T303-16, T303-19, and the switch, ConfigMap, offsite, grammar-parity and values-file-path tests.

<!-- block: local-development/tests/test_chart_recovery_mode.py | create -->

```python
"""Recovery mode in the chart (#303): `recovery.enabled` swaps the dashboard's command for the
chart's recovery script on the same pod and volume, drops the liveness probe, keeps the pod out of
the Service, and refuses what cannot be safe. Everything else renders as it did.

These shell out to `helm template` because the switch and its guards ARE Helm templating. The
script itself is tested in tests/test_recovery_mode.py.
"""

from __future__ import annotations

import importlib.util
import pathlib
import re
import shutil
import subprocess

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
CHART = REPO / "charts" / "group-sync-dashboard"
SCRIPT = CHART / "scripts" / "recovery_mode.py"
ON = {"recovery__enabled": "true"}
OFFSITE = {"backup__offsite__enabled": "true"}

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")


def render(*flags: str, **values):
    """Render the chart. Returns (ok, combined output). `__` in a key is `.`."""
    args = ["helm", "template", "t", str(CHART), "--set", "ingress.host=t.example.com", *flags]
    for key, value in values.items():
        args += ["--set", f"{key.replace('__', '.')}={value}"]
    done = subprocess.run(args, capture_output=True, text=True)
    return done.returncode == 0, done.stdout + done.stderr


def _docs(**values) -> list[dict]:
    ok, out = render(**values)
    assert ok, out
    return [d for d in yaml.safe_load_all(out) if d]


def _deployment(docs: list[dict]) -> dict:
    return next(d for d in docs if d["kind"] == "Deployment" and d["metadata"]["name"] == "t-group-sync-dashboard")


def _container(docs: list[dict], name: str = "dashboard") -> dict:
    return next(c for c in _deployment(docs)["spec"]["template"]["spec"]["containers"] if c["name"] == name)


def _env(container: dict) -> dict:
    return {e["name"]: e.get("value") for e in container["env"]}


def _key(doc: dict) -> tuple[str, str]:
    return doc["kind"], doc["metadata"]["name"]


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
    ok, out = render(replicaCount="2", leaderElection__enabled="false", reporting__enabled="false", **ON)
    assert not ok and "recovery.enabled=true requires replicaCount: 1 (it is 2)" in out
    ok, out = render(replicaCount="0", **ON)
    assert not ok and "requires replicaCount: 1 (it is 0)" in out
    # Codex F3: `int true` is 1, so a YAML boolean passed and rendered `replicas: true`
    ok, out = render(replicaCount="true", **ON)
    assert not ok and "requires replicaCount: 1 (it is true)" in out


@pytest.mark.parametrize("ttl,why", [("abc", "is not a duration"), ("-5m", "is not a duration"),
                                     ("7200", "is not a duration"), ("0", "is zero"), ("0s", "is zero")])
def test_t303_6_a_ttl_that_is_not_a_positive_duration_is_refused(ttl, why):
    ok, out = render(recovery__ttl=ttl, **ON)
    assert not ok and f'recovery.ttl "{ttl}" {why}' in out


def test_t303_7_recovery_without_a_volume_is_refused():
    ok, out = render(persistence__enabled="false", reporting__enabled="false", **ON)
    assert not ok and "recovery.enabled=true requires persistence.enabled=true" in out


def test_the_switch_is_read_as_a_word():
    ok, out = render("--set-string", "recovery.enabled=yes")
    assert not ok and 'recovery.enabled "yes" is not true or false' in out
    ok, quoted_false = render("--set-string", "recovery.enabled=false")
    assert ok and quoted_false == render()[1]


def test_t303_14_off_renders_exactly_the_default_and_the_dashboard_as_today():
    ok, default = render()
    assert ok, default
    assert render(recovery__enabled="false")[1] == default
    # `helm upgrade --reuse-values` from a chart without the block renders with no `recovery` key.
    assert render(recovery="null")[1] == default
    dashboard = _container(_docs())
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
    kinds = ("Role", "ClusterRole", "RoleBinding", "ClusterRoleBinding", "ServiceAccount")
    for extra in ({}, OFFSITE):
        off = sorted((yaml.safe_dump(d) for d in _docs(**extra) if d["kind"] in kinds))
        on = sorted((yaml.safe_dump(d) for d in _docs(**extra, **ON) if d["kind"] in kinds))
        assert off == on


def test_the_configmap_carries_the_script_verbatim():
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
      "backup__offsite__destination__s3__image__repository": "public.ecr.aws/aws-cli/aws-cli"}


@pytest.mark.parametrize("extra", [{}, {"backup__offsite__enabled": "false"}, OFFSITE,
                                   {**OFFSITE, "backup__offsite__destination__pvc__existingClaim": "my-offsite"},
                                   {**OFFSITE, **S3}], ids=["default", "off", "pvc", "existing-claim", "s3"])
def test_the_offsite_claim_is_mounted_exactly_when_the_cronjob_writes_one(extra):
    """The mount and the CronJob are decided by one switch today and by #304's helper next; whatever decides
    them, the recovery pod mounts the claim the CronJob writes, and nothing when it writes none. A default
    that turns offsite on (#304) must turn the mount on with it, or this test fails."""
    docs = _docs(**extra, **ON)
    mounted = [v["persistentVolumeClaim"]["claimName"] for v in _deployment(docs)["spec"]["template"]["spec"]["volumes"]
               if v["name"] == "offsite"]
    written = [v["persistentVolumeClaim"]["claimName"] for d in docs if d["kind"] == "CronJob"
               for v in d["spec"]["jobTemplate"]["spec"]["template"]["spec"]["volumes"]
               if v["name"] == "offsite" and "persistentVolumeClaim" in v]
    assert mounted == written, (mounted, written)


@pytest.mark.parametrize("ttl", ["2h", "90m", "1h30m", "1.5s", "250ms", "abc", "0", "0s", "-5m", "7200", "2H"])
def test_the_chart_and_the_script_accept_the_same_ttls(ttl):
    spec = importlib.util.spec_from_file_location("recovery_mode", SCRIPT)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    ok, out = render(recovery__ttl=ttl, **ON)
    assert ok == bool(script.ttl_seconds(ttl)), (ttl, out[-400:])


def _values_comment() -> str:
    lines = (CHART / "values.yaml").read_text().splitlines()
    end = lines.index("recovery:")
    start = max(i for i in range(end) if lines[i].startswith("# ---"))
    return "\n".join(lines[start:end])


def _between(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    return text[begin:text.index(end, begin + len(start))]


def test_t303_19_the_docs_name_the_switch_and_say_what_alerts():
    for doc in (CHART / "values.yaml", CHART / "README.md", REPO / "docs" / "RUNBOOK_backup_restore.md"):
        text = doc.read_text()
        assert "recovery.enabled" in text and "recovery.ttl" in text, doc
    comment = re.sub(r"\s*\n#\s*", " ", _values_comment())
    assert "values file" in comment and "deployment pipeline" in comment and "never with `oc set env`" in comment.lower()
    assert "GroupSyncDashboardNotPolling does not fire" in comment
    assert "GroupSyncDashboardReportSnapshotStale" in comment and "The TTL is the bound" in comment
    # what the TTL ends (measured: an exec'd process is killed when PID 1 exits) and what restarts it
    assert "every process in the container stops" in comment and "evicted" in comment and "0/1" in comment
    runbook = (REPO / "docs" / "RUNBOOK_backup_restore.md").read_text()
    assert "Check the time left first" in runbook and "every process in the container stops" in runbook
    for doc in (CHART / "README.md", REPO / "docs" / "RUNBOOK_backup_restore.md", CHART / "values.yaml"):
        assert not re.search(r"NotPolling[^.]*(fires|covers)[^.]*recovery", doc.read_text()), doc


def test_the_only_documented_path_is_the_values_file():
    """The operator's rule (2026-10-01): recovery mode is set in the release's values file and rolled out through
    the release's deployment pipeline. No Argo CD Application patch or parameter, no argocd or Helm command line
    in the operator's path; Argo CD is named only to say why a hand edit is reverted, and a plain `helm upgrade
    -f` only on the runbook's line for development and troubleshooting."""
    readme = (CHART / "README.md").read_text()
    runbook = _between((REPO / "docs" / "RUNBOOK_backup_restore.md").read_text(),
                       "**Recovery mode is the primary path", "**Without recovery mode**")
    assert runbook.count("**Development and troubleshooting only:**") == 1, "the plain Helm form has one labelled line"
    operator_path, development = runbook.split("**Development and troubleshooting only:**")
    texts = {
        "values comment": re.sub(r"\s*\n#\s*", " ", _values_comment()),
        "README section": _between(readme, "### Recovery mode", "\n#"),
        "README upgrading": _between(readme, "**To restore the database, before or after an upgrade", "## Uninstall"),
        "runbook": operator_path,
        "CHANGELOG": _between((REPO / "docs" / "CHANGELOG.md").read_text(), "- **Recovery mode:", "\n- **"),
    }
    for name, text in texts.items():
        assert "values file" in text, name
        assert not [word for word in ("helm upgrade", "--set", "--reset-then-reuse-values", "argocd",
                                      "applications.argoproj.io", "oc patch", "parameters") if word in text.lower()], name
        for sentence in re.split(r"(?<=[.;])\s+", text):
            assert "Argo CD" not in sentence or "revert" in sentence, (name, sentence)
    assert "helm upgrade $REL <chart> -n $NS -f <values-file>" in development and "--set" not in development
```

### Block 21 — local-development/tests/test_values_defaults.py: the stated false default

`recovery.enabled` joins `KEPT_OFF` with its reason (§3.1).

<!-- block: local-development/tests/test_values_defaults.py | edit -->

Old text:

```python
    "reporting.window.enabled": "P4: an operational rail the operator opts into (a timezone + hours + days); off = automated runs are never gated",
    "clusterConfig.secrets.writes.enabled": "S2 (#230): a write path on Secrets widens the dashboard's read-only posture; off until the operator turns it on — default pending the operator's A/B call of 2026-09-20; B flips the default and removes this exception",
```

New text:

```python
    "reporting.window.enabled": "P4: an operational rail the operator opts into (a timezone + hours + days); off = automated runs are never gated",
    "recovery.enabled": "#303: it stops the dashboard (the pod holds the data volume for a restore); an incident switch, never a default",
    "clusterConfig.secrets.writes.enabled": "S2 (#230): a write path on Secrets widens the dashboard's read-only posture; off until the operator turns it on — default pending the operator's A/B call of 2026-09-20; B flips the default and removes this exception",
```

