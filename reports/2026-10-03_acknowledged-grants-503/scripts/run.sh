#!/usr/bin/env bash
# SPEC_G3 §5 (#503, acknowledged direct grants) on the CRC lab, after
# reports/2026-10-03_platform-users-255/scripts/run.sh. #558 merged and Argo CD deployed it before the walk began,
# so "before" is taken by pointing the Application at a walk branch on main just before #558 (application 3.2.0),
# and "after" by pointing it back at main. In order:
#   1. The facts.
#   2. Before: the Application on lab/g3-before-walk (= <before sha>), the reads.
#   3. After: the Application back on main (= <merge sha>), the reads, and the self tier's read.
#   4. The screenshots, under a grant created after every read (so it is in no number), then deleted.
#   5. The facts again; the walk branch deleted.
#
#   KUBECONFIG=<the lab kubeconfig> scripts/run.sh <merge sha of #558> <main just before it>
#
# The reads are the dashboard's own, through the pod's loopback (X-Forwarded-User: the app's trust boundary, no login,
# no audit event): `dana.lee` (cluster-reader, the wide tier) for the numbers, `developer` (the self tier) for step 5
# of §5. Everything goes to walk.log, each command first.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
s="${here}/scripts"; log="${here}/walk.log"
repo="$(cd "${here}/../.." && pwd)"
ns=group-sync-dashboard; rel=group-sync-dashboard; app=group-sync-dashboard; argo_ns=openshift-gitops
branch=lab/g3-before-walk
label=walk.gsd.lab/run=acknowledged-503-2026-10-03
py=/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/.venv/bin/python
merged="${1:?the merge sha of #558}"; before="${2:?main just before #558}"
: "${KUBECONFIG:?}"
export KUBECONFIG PYTHONDONTWRITEBYTECODE=1
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
redact() { sed -E 's/sha256~[A-Za-z0-9_-]+/sha256~<redacted>/g'; }
note() { printf '\n## %s  (%s)\n' "$*" "$(now)" >> "${log}"; }
run() {
  printf '$ %s\n' "$*" >> "${log}"
  bash -c "$*" 2>&1 | redact >> "${log}" || echo "(exit ${PIPESTATUS[0]})" >> "${log}"
}
wait_for() {
  local what="$1" limit="$2" cond="$3" t0; t0=$(date +%s)
  while ! bash -c "${cond}" > /dev/null 2>&1; do
    if [ $(( $(date +%s) - t0 )) -ge "${limit}" ]; then echo "NOT MET within ${limit} s: ${what}" >> "${log}"; return 1; fi
    sleep 5
  done
  echo "met after $(( $(date +%s) - t0 )) s at $(now): ${what}" >> "${log}"
}
synced_on() { printf '%s' "oc get applications.argoproj.io -n ${argo_ns} ${app} -o jsonpath='{.status.sync.revision} {.status.sync.status} {.status.health.status} {.status.operationState.phase}' | grep -qx '$1 Synced Healthy Succeeded'"; }
runs_version() { printf '%s' "oc exec -n ${ns} deploy/${rel} -c dashboard -- curl -s http://127.0.0.1:8080/api/version | jq -e --arg v '$1' '.version == \$v'"; }
refreshed() { printf '%s' "oc logs -n ${ns} deploy/${rel} -c dashboard --since=10m | grep -qE 'dashboard: [0-9]+ direct-user binding'"; }
as() { printf '%s' "oc exec -n ${ns} deploy/${rel} -c dashboard -- curl -s -H 'X-Forwarded-User: $1' 'http://127.0.0.1:8080$2'"; }
facts() {
  run "oc get persistentvolumeclaims -n ${ns} -o custom-columns=NAME:.metadata.name,UID:.metadata.uid"
  run "oc get applications.argoproj.io -n ${argo_ns} ${app} -o json | jq -c '{rev: .spec.source.targetRevision, sync: .status.sync.status, health: .status.health.status, synced: .status.sync.revision, op: .status.operationState.phase, retries: .status.operationState.retryCount}'"
  run "oc exec -n ${ns} deploy/${rel} -c dashboard -- curl -s http://127.0.0.1:8080/api/version | jq -c '{version, commit}'"
}
reads() {  # <stage>: the numbers §5 names, as dana.lee, and the /metrics series
  note "reads: $1"
  run "oc logs -n ${ns} deploy/${rel} -c dashboard --since=10m | grep -E 'dashboard: [0-9]+ direct-user binding' | tail -1"
  run "$(as dana.lee /api/clusters/dashboard/user-bindings) | jq -c '{scope, total, excluded_platform, acknowledged, acknowledged_bindings: [(.acknowledged_bindings // [])[] | {name, namespace, user, managed_source}]}'"
  run "$(as dana.lee /api/alerts) | jq -c '[(.alerts // .)[] | select(.kind == \"direct_user_binding\" and .cluster == \"dashboard\") | .subject]'"
  run "$(as dana.lee /api/clusters/dashboard/namespaces) | jq -c '{cluster_wide_grants: (.cluster_wide_grants | if type == \"array\" then length else . end), platform_with_findings: (.platform_with_findings | if type == \"array\" then [.[] | (.name // .)] else . end), gso_direct_grants: [.namespaces[] | select(.name == \"group-sync-operator\") | .direct_grants]}'"
  run "curl -sk https://\$(oc get routes.route.openshift.io -n ${ns} ${rel} -o jsonpath='{.status.ingress[0].host}')/metrics | grep -E '^gsd_alerts_total\\{cluster=\"dashboard\",kind=\"direct_user_binding\"\\}|^gsd_bindings_total\\{cluster=\"(dashboard|shared-rnd|shared-qa)\",finding=\"unmanaged\"\\}'"
}
deploy_and_wait() {  # <sha> <version> <what>
  wait_for "the Application synced $3" 900 "$(synced_on "$1")" || rc=1
  run "oc rollout status -n ${ns} deploy/${rel} --timeout=10m"
  wait_for "the pod runs $2" 300 "$(runs_version "$2")" || rc=1
  wait_for "a refresh line for dashboard after $3" 600 "$(refreshed)" || rc=1
}

{ echo "# SPEC_G3 §5 walk (#503), CRC lab; written by scripts/run.sh"; echo "# started $(now); kube context $(oc config current-context); merge ${merged}; before ${before}"; } > "${log}"
rc=0

cleanup() {
  { printf '\n## exit trap  (%s)\n' "$(now)"
    oc delete clusterrolebindings.rbac.authorization.k8s.io,clusterroles.rbac.authorization.k8s.io -l "${label}" --ignore-not-found 2>&1
    target=$(oc get applications.argoproj.io -n ${argo_ns} ${app} -o jsonpath='{.spec.source.targetRevision}')
    echo "targetRevision: ${target}"
    if [ "${target}" != main ]; then
      (cd "${repo}" && local-development/release-crc.sh --argocd main --values environments/crc.yaml 2>&1 | tail -4) || true
      echo "targetRevision now: $(oc get applications.argoproj.io -n ${argo_ns} ${app} -o jsonpath='{.spec.source.targetRevision}')"
    fi
    git -C "${repo}" push -q origin --delete "${branch}" 2>&1 || true
  } >> "${log}"
}
trap cleanup EXIT

note "Step 1: the facts (the Application already on the merge)"
facts

note "Step 2: before, the Application on ${branch} = ${before} (application 3.2.0)"
run "git -C '${repo}' push -q origin ${before}:refs/heads/${branch} && echo pushed ${branch} at ${before}"
run "cd '${repo}' && local-development/release-crc.sh --argocd ${branch} --values environments/crc.yaml 2>&1 | tail -6"
deploy_and_wait "${before}" 3.2.0 "the before revision"
reads "before"

note "Step 3: after, the Application back on main = ${merged} (application 3.3.0)"
run "cd '${repo}' && local-development/release-crc.sh --argocd main --values environments/crc.yaml 2>&1 | tail -6"
deploy_and_wait "${merged}" 3.3.0 "the merge"
reads "after"
note "Step 3: the self tier, as developer (no grant)"
run "$(as developer /api/clusters/dashboard/user-bindings) | jq -c '{scope, total, acknowledged, acknowledged_bindings, acknowledged_truncated, own: [.bindings[] | {name, namespace}]}'"

note "Step 4: the screenshots, under a grant created after every read"
run "oc create -f '${s}/grant.yaml'"
sleep 70; echo "waited 70 s for the tier's cache until $(now)" >> "${log}"
printf '$ %s\n' "GSD_UI_PASSWORD=<from crc console --credentials> ${py} scripts/shots.py" >> "${log}"
GSD_UI_PASSWORD="$(crc console --credentials -o json | jq -r .clusterConfig.developerCredentials.password)" "${py}" "${s}/shots.py" 2>&1 | redact >> "${log}" || rc=$?
run "oc delete -f '${s}/grant.yaml'"

note "Step 5: after"
facts
echo "walk exit=${rc} at $(now)" >> "${log}"
exit "${rc}"
