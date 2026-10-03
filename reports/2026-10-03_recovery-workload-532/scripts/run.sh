#!/usr/bin/env bash
# SPEC_E11 §5 (#532, recovery mode as its own workload) on the CRC lab, end to end. The lab is a development
# environment, so the CLI forms SPEC_E11 §5 names are allowed here. In order:
#   1. Before: the PVC UIDs, the Application, both Deployments (the recovery one 0/0).
#   2. Recovery on, through the values file: a walk branch from the merge, with `recovery.enabled: true` in
#      environments/crc.yaml, pushed, and the Application pointed at it with release-crc.sh --argocd.
#   3. restore-db.sh --list against the recovery pod.
#   4. Recovery off, through the values file: a commit on the walk branch, pushed. Measured from the push to the
#      app pod Ready.
#   5. Runbook §4d once, its own commands.
#   6. The Application back on main, the walk branch deleted, and the PVC UIDs again.
#
#   KUBECONFIG=<the lab kubeconfig> scripts/run.sh <merge sha of #551>
#
# Everything goes to walk.log, each command first. Nothing prints a token or a password. The cluster writes are
# release-crc.sh's (the Application's revision), §4d's own pause, scale and give-back, and nothing else.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
log="${here}/walk.log"
repo="$(cd "${here}/../.." && pwd)"
ns=group-sync-dashboard; rel=group-sync-dashboard; app=group-sync-dashboard; argo_ns=openshift-gitops
branch=lab/e11-recovery-walk
merged="${1:?the merge sha of #551}"
: "${KUBECONFIG:?}"
export KUBECONFIG
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
redact() { sed -E 's/sha256~[A-Za-z0-9_-]+/sha256~<redacted>/g'; }
note() { printf '\n## %s  (%s)\n' "$*" "$(now)" >> "${log}"; }
run() {  # the command line, then its output; a failing command is recorded, not fatal
  printf '$ %s\n' "$*" >> "${log}"
  bash -c "$*" 2>&1 | redact >> "${log}" || echo "(exit ${PIPESTATUS[0]})" >> "${log}"
}
appstate="oc get applications.argoproj.io -n ${argo_ns} ${app} -o json | jq -c '{rev: .spec.source.targetRevision, sync: .status.sync.status, health: .status.health.status, synced: .status.sync.revision, op: .status.operationState.phase, retries: .status.operationState.retryCount, started: .status.operationState.startedAt, finished: .status.operationState.finishedAt, automated: .spec.syncPolicy.automated, history: [.status.history[-3:][]? | {rev: .revision[0:10], deployStartedAt, deployedAt}]}'"
deploys="oc get deployments.apps -n ${ns} ${rel} ${rel}-recovery -o custom-columns=NAME:.metadata.name,WANT:.spec.replicas,READY:.status.readyReplicas,AVAILABLE:.status.availableReplicas"
pods="oc get pods -n ${ns} -l 'app in (${rel},${rel}-recovery)' -o custom-columns=NAME:.metadata.name,APP:.metadata.labels.app,PHASE:.status.phase,START:.status.startTime,DELETING:.metadata.deletionTimestamp"
facts() {
  run "oc get persistentvolumeclaims -n ${ns} -o custom-columns=NAME:.metadata.name,UID:.metadata.uid"
  run "${appstate}"; run "${deploys}"; run "${pods}"
}
# wait_for <what> <seconds> <bash condition>: polls every 5 s, records when it held or that it never did
wait_for() {
  local what="$1" limit="$2" cond="$3" t0; t0=$(date +%s)
  while ! bash -c "${cond}" > /dev/null 2>&1; do
    if [ $(( $(date +%s) - t0 )) -ge "${limit}" ]; then echo "NOT MET within ${limit} s: ${what}" >> "${log}"; return 1; fi
    sleep 5
  done
  echo "met after $(( $(date +%s) - t0 )) s at $(now): ${what}" >> "${log}"
}
ready() {  # <deployment> <replicas>: the Deployment wants that count and has that many ready (absent counts as 0)
  printf '%s' "oc get deployments.apps -n ${ns} $1 -o json | jq -e '(.spec.replicas == $2) and ((.status.readyReplicas // 0) == $2)'"
}
synced_on() {  # <sha>: the Application synced that revision, Healthy, with its operation Succeeded
  printf '%s' "oc get applications.argoproj.io -n ${argo_ns} ${app} -o jsonpath='{.status.sync.revision} {.status.sync.status} {.status.health.status} {.status.operationState.phase}' | grep -qx '$1 Synced Healthy Succeeded'"
}

{ echo "# SPEC_E11 §5 walk (#532), CRC lab; written by scripts/run.sh"; echo "# started $(now); kube context $(oc config current-context); merge ${merged}"; } > "${log}"
rc=0
wt="$(mktemp -d)/walk-branch"

cleanup() {  # whatever state the run stopped in: Argo back on main, automated sync on, the walk branch gone
  { printf '\n## exit trap  (%s)\n' "$(now)"
    oc patch applications.argoproj.io/${app} -n ${argo_ns} --type json -p '[{"op":"remove","path":"/spec/syncPolicy/automated/enabled"}]' 2>&1 || true
    target=$(oc get applications.argoproj.io -n ${argo_ns} ${app} -o jsonpath='{.spec.source.targetRevision}')
    echo "targetRevision: ${target}"
    if [ "${target}" != main ]; then
      (cd "${repo}" && local-development/release-crc.sh --argocd main --values environments/crc.yaml 2>&1 | tail -4) || true
      echo "targetRevision now: $(oc get applications.argoproj.io -n ${argo_ns} ${app} -o jsonpath='{.spec.source.targetRevision}')"
    fi
    git -C "${repo}" worktree remove --force "${wt}" 2>&1 || true
    git -C "${repo}" branch -D "${branch}" 2>&1 || true   # the walk's own local branch; the remote one is deleted in step 6
  } >> "${log}"
}
trap cleanup EXIT

note "Step 1: before (the Application on main at the merge)"
facts
wait_for "the Application synced the merge" 900 "$(synced_on "${merged}")" || rc=1
run "${deploys}"

note "Step 2: recovery on, through the values file on ${branch}"
git -C "${repo}" fetch -q origin
git -C "${repo}" worktree add -q -b "${branch}" "${wt}" "${merged}"
printf '\n# SPEC_E11 §5 walk only: recovery mode through the values file (never merged).\nrecovery:\n  enabled: true\n' >> "${wt}/environments/crc.yaml"
git -C "${wt}" commit -q -am "lab walk (#532): recovery.enabled: true" && on_sha=$(git -C "${wt}" rev-parse HEAD)
run "git -C '${wt}' push -q -u origin ${branch} && echo pushed ${on_sha} at \$(date -u +%H:%M:%SZ)"
run "cd '${repo}' && local-development/release-crc.sh --argocd ${branch} --values environments/crc.yaml 2>&1 | tail -15"
wait_for "the Application synced recovery-on" 900 "$(synced_on "${on_sha}")" || rc=1
wait_for "recovery 1/1 and the app 0" 600 "$(ready "${rel}-recovery" 1) && $(ready "${rel}" 0)" || rc=1
facts
run "oc get events -n ${ns} --field-selector involvedObject.kind=Pod -o custom-columns=TIME:.lastTimestamp,OBJECT:.involvedObject.name,REASON:.reason,MESSAGE:.message --sort-by=.lastTimestamp | grep -E '${rel}-recovery' | tail -12"

note "Step 3: restore-db.sh --list against the recovery pod"
run "cd '${repo}' && local-development/restore-db.sh --list --namespace ${ns} --release ${rel} 2>&1 | head -40"

note "Step 4: recovery off, through the values file"
sed -i '' 's/^  enabled: true$/  enabled: false/' "${wt}/environments/crc.yaml"
git -C "${wt}" commit -q -am "lab walk (#532): recovery.enabled: false" && off_sha=$(git -C "${wt}" rev-parse HEAD)
pushed=$(date +%s)
run "git -C '${wt}' push -q origin ${branch} && echo pushed ${off_sha} at \$(date -u +%H:%M:%SZ)"
wait_for "the Application synced recovery-off" 900 "$(synced_on "${off_sha}")" || rc=1
wait_for "the app 1/1 and recovery 0" 600 "$(ready "${rel}" 1) && $(ready "${rel}-recovery" 0)" || rc=1
echo "recovery off: $(( $(date +%s) - pushed )) s from the push to the app Ready, polling included" >> "${log}"
facts
run "oc get events -n ${ns} --field-selector involvedObject.kind=Pod -o custom-columns=TIME:.lastTimestamp,OBJECT:.involvedObject.name,REASON:.reason,MESSAGE:.message --sort-by=.lastTimestamp | grep -E '${rel}-(recovery-)?[a-z0-9]+-[a-z0-9]+ ' | tail -14"

note "Step 5: runbook §4d once (its own commands, APP=${app})"
ctrl=$(oc get pods -n ${argo_ns} -l app.kubernetes.io/name=openshift-gitops-application-controller -o jsonpath='{.items[0].metadata.name}')
oc logs -f -n ${argo_ns} "${ctrl}" --since=1s 2>&1 | grep --line-buffered -E "application=(${argo_ns}/)?${app}[ \"]" > "${here}/argo-controller-4d.log" &
tailer=$!
echo "the controller's log for ${app} goes to argo-controller-4d.log from $(now) (pod ${ctrl})" >> "${log}"
run "oc get deploy -n ${ns} ${rel} -o jsonpath='{.metadata.annotations.argocd\\.argoproj\\.io/tracking-id}{\"\\n\"}'"
run "oc patch application.argoproj.io/${app} -n ${argo_ns} --type merge -p '{\"spec\":{\"syncPolicy\":{\"automated\":{\"enabled\":false}}}}'"
run "oc get application.argoproj.io/${app} -n ${argo_ns} -o jsonpath='{.spec.syncPolicy.automated.enabled} {.status.operationState.phase}{\"\\n\"}'"
run "oc scale -n ${ns} deploy/${rel} --replicas=0"
run "oc scale -n ${ns} deploy/${rel}-recovery --replicas=1"
wait_for "§4d: recovery 1/1 and the app 0" 600 "$(ready "${rel}-recovery" 1) && $(ready "${rel}" 0)" || rc=1
run "cd '${repo}' && local-development/restore-db.sh --list --namespace ${ns} --release ${rel} 2>&1 | head -12"
run "oc patch application.argoproj.io/${app} -n ${argo_ns} --type json -p '[{\"op\":\"remove\",\"path\":\"/spec/syncPolicy/automated/enabled\"}]'"
run "oc wait application.argoproj.io/${app} -n ${argo_ns} --for=jsonpath='{.status.sync.status}'=Synced --timeout=5m"
run "oc rollout status -n ${ns} deploy/${rel} --timeout=10m"
wait_for "§4d given back: the app 1/1 and recovery 0" 600 "$(ready "${rel}" 1) && $(ready "${rel}-recovery" 0)" || rc=1
run "${deploys}"
run "${appstate}"
kill "${tailer}" 2>/dev/null || true
echo "argo-controller-4d.log: $(wc -l < "${here}/argo-controller-4d.log" | tr -d ' ') lines" >> "${log}"
run "oc get events -n ${ns} --sort-by=.lastTimestamp -o custom-columns=TIME:.lastTimestamp,OBJECT:.involvedObject.name,REASON:.reason,MESSAGE:.message | grep -E '${rel}' | tail -20"

note "Step 6: the Application back on main, the walk branch deleted, after"
run "cd '${repo}' && local-development/release-crc.sh --argocd main --values environments/crc.yaml 2>&1 | tail -8"
wait_for "the Application back on main and synced" 900 "$(synced_on "${merged}")" || rc=1
run "git -C '${repo}' push -q origin --delete ${branch} && echo deleted ${branch}"
facts
echo "walk exit=${rc} at $(now)" >> "${log}"
exit "${rc}"
