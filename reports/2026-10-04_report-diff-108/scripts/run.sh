#!/usr/bin/env bash
# SPEC_F3 §5 (#108, report-diff runs) on the CRC lab, end to end:
#   1. the before-facts; wait for application 4.3.0 to be running;
#   2. two namespace-access runs of demo-qa as dana.lee (viewer runs, through a ticket on the pod loopbacks);
#   3. under the labelled grant, walk.py diffs the second against the first through the page: "No change";
#   4. plant one RoleBinding (planted.yaml); wait until the dashboard's binding refresh counts it (the unmanaged
#      bindings metric moves), then one snapshot interval;
#   5. a third run; walk.py diffs it against the second: the binding's rows added, counts moved, nothing else;
#   6. remove the planted binding and the grant (also the exit trap, by the label); the after-facts.
#
#   KUBECONFIG=<the lab kubeconfig> scripts/run.sh
#
# Everything goes to walk.log beside this folder's README. The ticket goes to the report pod on stdin only; the UI
# password goes to walk.py through its environment only; neither is printed.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"; s="${here}/scripts"; log="${here}/walk.log"
ns=group-sync-dashboard; label=walk.gsd.lab/run=report-diff-108-2026-10-04; viewer=dana.lee
params='{"namespaces": "demo-qa"}'
py=/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/.venv/bin/python
: "${KUBECONFIG:?}"; export KUBECONFIG PYTHONDONTWRITEBYTECODE=1
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
pw() { crc console --credentials -o json | jq -r .clusterConfig.developerCredentials.password; }
note() { printf '\n## %s  (%s)\n' "$*" "$(now)" >> "${log}"; }
run() { printf '$ %s\n' "$*" >> "${log}"; bash -c "$*" >> "${log}" 2>&1 || echo "(exit $?)" >> "${log}"; }
dash() { oc exec -n "${ns}" deploy/group-sync-dashboard -c dashboard -- python3.14 -c "
import sys, urllib.request
req = urllib.request.Request('http://127.0.0.1:8080' + sys.argv[1], headers={'X-Forwarded-User': sys.argv[2]})
print(urllib.request.urlopen(req, timeout=30).read().decode())" "$1" "${viewer}"; }
unmanaged() { dash /metrics | awk '/^gsd_bindings_total\{cluster="dashboard",finding="unmanaged"\}/ {print int($2)}'; }
new_run() {  # one viewer run of namespace-access on demo-qa; prints its id
  local ticket out
  ticket=$(dash /api/report/ticket | python3 -c 'import json,sys; print(json.load(sys.stdin)["ticket"])')
  out=$(printf '%s\n%s\n%s\n%s\n%s\n' "${viewer}" "${ticket}" dashboard namespace-access "${params}" \
        | oc exec -i -n "${ns}" deploy/group-sync-dashboard-report -c report -- python3.14 -c "$(cat "${s}/in_pod.py")")
  echo "${out}" >> "${log}"
  python3 -c 'import json,sys; r=json.loads(sys.argv[1]); assert r["status"]=="done", r; print(r["id"])' "${out}"
}
page() {  # walk.py under the grant, which exists only for this step
  run "oc apply -f '${s}/grant.yaml'"; sleep 70
  printf '$ %s\n' "GSD_UI_PASSWORD=<from crc console --credentials> ${py} scripts/walk.py $*" >> "${log}"
  GSD_UI_PASSWORD="$(pw)" "${py}" "${s}/walk.py" "$@" >> "${log}" 2>&1 || rc=1
  run "oc delete -f '${s}/grant.yaml' --ignore-not-found"
}
facts() {
  run "oc get persistentvolumeclaims -n ${ns} -o custom-columns=NAME:.metadata.name,UID:.metadata.uid"
  run "oc get applications.argoproj.io -n openshift-gitops group-sync-dashboard -o json | jq -c '{sync: .status.sync.status, health: .status.health.status, revision: .status.sync.revision}'"
  run "oc get pods -n ${ns} -l app.kubernetes.io/instance=group-sync-dashboard -o 'custom-columns=NAME:.metadata.name,START:.status.startTime,IMAGE:.spec.containers[0].image' | grep -vE 'offsite-|verify-'"
  run "oc get rolebindings.rbac.authorization.k8s.io -n demo-qa -o 'custom-columns=NAME:.metadata.name,ROLE:.roleRef.name,SUBJECTS:.subjects[*].name'"
  run "oc auth can-i update clusterrolebindings.rbac.authorization.k8s.io --as=developer 2>/dev/null || true"
  run "oc get clusterroles.rbac.authorization.k8s.io,clusterrolebindings.rbac.authorization.k8s.io,rolebindings.rbac.authorization.k8s.io -A -l ${label} -o name"
}
sweep() { oc delete clusterrolebindings.rbac.authorization.k8s.io,clusterroles.rbac.authorization.k8s.io -l "${label}" --ignore-not-found >/dev/null 2>&1 || true
          oc delete rolebindings.rbac.authorization.k8s.io -n demo-qa -l "${label}" --ignore-not-found >/dev/null 2>&1 || true; }

echo "# SPEC_F3 §5 walk (#108), CRC lab; written by scripts/run.sh; started $(now)" > "${log}"
rc=0; trap sweep EXIT
note "Wait for application 4.3.0"
for _ in $(seq 1 90); do
  [ "$(oc get pods -n ${ns} -l app.kubernetes.io/instance=group-sync-dashboard -o jsonpath='{range .items[*]}{.spec.containers[0].image}{" "}{.status.containerStatuses[0].ready}{"\n"}{end}' | grep -cE ':4\.3\.0 true')" -ge 2 ] && break
  sleep 20
done
note "Before"; facts
echo "unmanaged bindings now: $(unmanaged)" >> "${log}"
note "Two runs of namespace-access on demo-qa, over the same data"
a=$(new_run); b=$(new_run); echo "A=${a} B=${b}" >> "${log}"
note "Phase 1: diff B against A through the page (expect No change)"
page "${b}" "${a}" phase1 none
note "Plant one RoleBinding"
before=$(unmanaged); echo "unmanaged bindings before the plant: ${before}" >> "${log}"
run "oc apply -f '${s}/planted.yaml'"
note "Wait for the binding refresh to count it (the unmanaged metric moves), then one snapshot interval"
for _ in $(seq 1 100); do [ "$(unmanaged)" -gt "${before}" ] && break; sleep 60; done
echo "unmanaged bindings after the refresh: $(unmanaged) at $(now)" >> "${log}"
sleep 330
note "Phase 2: a third run, diffed against B through the page (expect the binding added)"
c=$(new_run); echo "C=${c}" >> "${log}"
page "${c}" "${b}" phase2 planted
note "Remove the planted binding"
run "oc delete -f '${s}/planted.yaml' --ignore-not-found"
note "After"; facts
echo "walk exit ${rc}" >> "${log}"
exit "${rc}"
