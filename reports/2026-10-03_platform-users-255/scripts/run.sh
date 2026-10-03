#!/usr/bin/env bash
# SPEC_G2 §5 (#255, platform users per estate) on the CRC lab, end to end, after
# reports/2026-10-03_recovery-workload-532/scripts/run.sh. The lab is a development environment, so the CLI forms are
# allowed here. In order:
#   1. Before: the facts, the grant (developer passes the wide tier for the dashboard's own reads), the numbers.
#   2. Add: `platformUsers.additionalNames: ["tmp-contractor-9931"]` in environments/crc.yaml on a walk branch,
#      pushed, the Application pointed at it with release-crc.sh --argocd; the numbers after the refresh.
#   3. Stale: `ghost-9931` beside it; the numbers, and shots.py's screenshots of the Namespace audit tab.
#   4. Remove: environments/crc.yaml back to the merge's content; the numbers again.
#   5. After: the Application back on main, the walk branch deleted, the grant deleted, the facts.
#
#   KUBECONFIG=<the lab kubeconfig> scripts/run.sh <merge sha of #556>
#
# Everything goes to walk.log, each command first. The numbers are the dashboard's own, read through the pod's
# loopback as `developer` (X-Forwarded-User, the app's trust boundary; no login, no audit event) and from the public
# /metrics. developer's UI password (for shots.py only) is read from `crc console --credentials` into its environment,
# never printed.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
s="${here}/scripts"; log="${here}/walk.log"
repo="$(cd "${here}/../.." && pwd)"
ns=group-sync-dashboard; rel=group-sync-dashboard; app=group-sync-dashboard; argo_ns=openshift-gitops
branch=lab/g2-platform-users-walk
label=walk.gsd.lab/run=platform-users-255-2026-10-03
py=/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/.venv/bin/python
merged="${1:?the merge sha of #556}"
: "${KUBECONFIG:?}"
export KUBECONFIG PYTHONDONTWRITEBYTECODE=1
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
redact() { sed -E 's/sha256~[A-Za-z0-9_-]+/sha256~<redacted>/g'; }
note() { printf '\n## %s  (%s)\n' "$*" "$(now)" >> "${log}"; }
run() {
  printf '$ %s\n' "$*" >> "${log}"
  bash -c "$*" 2>&1 | redact >> "${log}" || echo "(exit ${PIPESTATUS[0]})" >> "${log}"
}
wait_for() {  # <what> <seconds> <bash condition>
  local what="$1" limit="$2" cond="$3" t0; t0=$(date +%s)
  while ! bash -c "${cond}" > /dev/null 2>&1; do
    if [ $(( $(date +%s) - t0 )) -ge "${limit}" ]; then echo "NOT MET within ${limit} s: ${what}" >> "${log}"; return 1; fi
    sleep 5
  done
  echo "met after $(( $(date +%s) - t0 )) s at $(now): ${what}" >> "${log}"
}
synced_on() { printf '%s' "oc get applications.argoproj.io -n ${argo_ns} ${app} -o jsonpath='{.status.sync.revision} {.status.sync.status} {.status.health.status} {.status.operationState.phase}' | grep -qx '$1 Synced Healthy Succeeded'"; }
pod_started() { oc get pods -n ${ns} -l app=${rel} -o jsonpath='{.items[0].status.startTime}'; }
refreshed_since() {  # a refresh line for `dashboard` from the current app pod
  printf '%s' "oc logs -n ${ns} deploy/${rel} -c dashboard --since=10m | grep -qE 'dashboard: [0-9]+ direct-user binding'"
}
facts() {
  run "oc get persistentvolumeclaims -n ${ns} -o custom-columns=NAME:.metadata.name,UID:.metadata.uid"
  run "oc get applications.argoproj.io -n ${argo_ns} ${app} -o json | jq -c '{rev: .spec.source.targetRevision, sync: .status.sync.status, health: .status.health.status, synced: .status.sync.revision, op: .status.operationState.phase, retries: .status.operationState.retryCount}'"
  run "oc get pods -n ${ns} -l app=${rel} -o custom-columns=NAME:.metadata.name,START:.status.startTime,IMAGE:.spec.containers[0].image"
  run "oc exec -n ${ns} deploy/${rel} -c dashboard -- curl -s http://127.0.0.1:8080/api/version | jq -c '{version, commit}'"
}
numbers() {  # <stage>: the three numbers §5 names, the stale list, and the refresh line they follow
  note "numbers: $1"
  run "oc logs -n ${ns} deploy/${rel} -c dashboard --since=10m | grep -E 'dashboard: [0-9]+ direct-user binding' | tail -1"
  run "oc exec -n ${ns} deploy/${rel} -c dashboard -- curl -s -H 'X-Forwarded-User: developer' 'http://127.0.0.1:8080/api/clusters/dashboard/user-bindings' | jq -c '{scope, total, excluded_platform, platform_users_unmatched, note}'"
  run "curl -sk https://\$(oc get routes.route.openshift.io -n ${ns} ${rel} -o jsonpath='{.status.ingress[0].host}')/metrics | grep -E '^gsd_bindings_total\\{cluster=\"dashboard\",finding=\"unmanaged\"\\}'"
}
deploy_and_wait() {  # <sha> <what>
  wait_for "the Application synced $2" 900 "$(synced_on "$1")" || rc=1
  run "oc rollout status -n ${ns} deploy/${rel} --timeout=10m"
  wait_for "a refresh line for dashboard after $2" 600 "$(refreshed_since)" || rc=1
}

{ echo "# SPEC_G2 §5 walk (#255), CRC lab; written by scripts/run.sh"; echo "# started $(now); kube context $(oc config current-context); merge ${merged}"; } > "${log}"
rc=0
wt="$(mktemp -d)/walk-branch"

cleanup() {
  { printf '\n## exit trap  (%s)\n' "$(now)"
    oc delete clusterrolebindings.rbac.authorization.k8s.io,clusterroles.rbac.authorization.k8s.io -l "${label}" --ignore-not-found 2>&1
    echo "can-i list crb after the trap: $(oc auth can-i list clusterrolebindings.rbac.authorization.k8s.io --as=developer 2>/dev/null || true)"
    target=$(oc get applications.argoproj.io -n ${argo_ns} ${app} -o jsonpath='{.spec.source.targetRevision}')
    echo "targetRevision: ${target}"
    if [ "${target}" != main ]; then
      (cd "${repo}" && local-development/release-crc.sh --argocd main --values environments/crc.yaml 2>&1 | tail -4) || true
      echo "targetRevision now: $(oc get applications.argoproj.io -n ${argo_ns} ${app} -o jsonpath='{.spec.source.targetRevision}')"
    fi
    git -C "${repo}" worktree remove --force "${wt}" 2>&1 || true
    git -C "${repo}" branch -D "${branch}" 2>&1 || true
    git -C "${repo}" push -q origin --delete "${branch}" 2>&1 || true
  } >> "${log}"
}
trap cleanup EXIT

note "Step 1: before"
facts
wait_for "the Application synced the merge" 900 "$(synced_on "${merged}")" || rc=1
run "oc create -f '${s}/grant.yaml'"
run "oc auth can-i list clusterrolebindings.rbac.authorization.k8s.io --as=developer"
sleep 70; echo "waited 70 s for the tier's cache until $(now)" >> "${log}"
run "oc exec -n ${ns} deploy/${rel} -c dashboard -- curl -s -H 'X-Forwarded-User: developer' http://127.0.0.1:8080/api/whoami | jq -c '{scope: .visibility.scope, cluster_admin: .visibility.cluster_admin}'"
numbers "before"

note "Step 2: add tmp-contractor-9931 through the values file on ${branch}"
git -C "${repo}" fetch -q origin
git -C "${repo}" worktree add -q -b "${branch}" "${wt}" "${merged}"
cp "${wt}/environments/crc.yaml" "${wt}/.crc.yaml.merged"
printf '\n# SPEC_G2 §5 walk only (never merged).\nplatformUsers:\n  additionalNames: ["tmp-contractor-9931"]\n' >> "${wt}/environments/crc.yaml"
git -C "${wt}" commit -q environments/crc.yaml -m "lab walk (#255): platformUsers.additionalNames tmp-contractor-9931" && add_sha=$(git -C "${wt}" rev-parse HEAD)
run "git -C '${wt}' push -q -u origin ${branch} && echo pushed ${add_sha} at \$(date -u +%H:%M:%SZ)"
run "cd '${repo}' && local-development/release-crc.sh --argocd ${branch} --values environments/crc.yaml 2>&1 | tail -6"
deploy_and_wait "${add_sha}" "the add"
numbers "add"

note "Step 3: stale ghost-9931 beside it"
sed -i '' 's/additionalNames: \["tmp-contractor-9931"\]/additionalNames: ["tmp-contractor-9931", "ghost-9931"]/' "${wt}/environments/crc.yaml"
git -C "${wt}" commit -q environments/crc.yaml -m "lab walk (#255): ghost-9931, a name nothing binds" && stale_sha=$(git -C "${wt}" rev-parse HEAD)
run "git -C '${wt}' push -q origin ${branch} && echo pushed ${stale_sha} at \$(date -u +%H:%M:%SZ)"
deploy_and_wait "${stale_sha}" "the stale name"
numbers "stale"
printf '$ %s\n' "GSD_UI_PASSWORD=<from crc console --credentials> ${py} scripts/shots.py" >> "${log}"
GSD_UI_PASSWORD="$(crc console --credentials -o json | jq -r .clusterConfig.developerCredentials.password)" "${py}" "${s}/shots.py" 2>&1 | redact >> "${log}" || rc=$?

note "Step 4: remove, environments/crc.yaml back to the merge's content"
cp "${wt}/.crc.yaml.merged" "${wt}/environments/crc.yaml"
git -C "${wt}" commit -q environments/crc.yaml -m "lab walk (#255): back to the merge's values" && back_sha=$(git -C "${wt}" rev-parse HEAD)
run "git -C '${wt}' diff --stat ${merged} ${back_sha} -- environments/crc.yaml; echo '(no diff = identical to the merge)'"
run "git -C '${wt}' push -q origin ${branch} && echo pushed ${back_sha} at \$(date -u +%H:%M:%SZ)"
deploy_and_wait "${back_sha}" "the removal"
numbers "removed"

note "Step 5: after, the Application back on main"
run "oc delete -f '${s}/grant.yaml'"
run "cd '${repo}' && local-development/release-crc.sh --argocd main --values environments/crc.yaml 2>&1 | tail -6"
wait_for "the Application back on main and synced" 900 "$(synced_on "${merged}")" || rc=1
facts
echo "walk exit=${rc} at $(now)" >> "${log}"
exit "${rc}"
