#!/usr/bin/env bash
# SPEC_G4 §5 step 1 (#420) on the CRC lab: the namespaced Leases Role and RoleBinding are live, nothing is narrowed,
# the elector's Lease renews, and no Lease error is logged. Then one check §5 does not list, for the operator's
# condition on step 2: a throwaway ServiceAccount bound ONLY to the new Role gets the three Lease verbs in the release
# namespace and none outside it. While the ClusterRole's rule exists, no renewal can be attributed to the Role, so
# this is the Role's sufficiency, and step 2's own walk (T420-8) is the renewal with the rule gone.
#   KUBECONFIG=<the lab kubeconfig> scripts/run.sh <merge sha of #560>
# The cluster writes are the probe's ServiceAccount and RoleBinding (labelled, deleted, and swept by the exit trap).
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"; log="${here}/walk.log"
ns=group-sync-dashboard; sa=group-sync-dashboard; argo_ns=openshift-gitops
label=walk.gsd.lab/run=leases-role-420-2026-10-03
merged="${1:?the merge sha of #560}"
: "${KUBECONFIG:?}"; export KUBECONFIG
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
note() { printf '\n## %s  (%s)\n' "$*" "$(now)" >> "${log}"; }
run() { printf '$ %s\n' "$*" >> "${log}"; bash -c "$*" >> "${log}" 2>&1 || echo "(exit ${PIPESTATUS[0]})" >> "${log}"; }
canis() {  # <as> <namespace>: the three verbs
  for v in get create update; do printf '%s %s in %s: %s\n' "$1" "${v}" "$2" "$(oc auth can-i "${v}" leases.coordination.k8s.io --as "$1" -n "$2" 2>/dev/null || true)"; done
}
{ echo "# SPEC_G4 §5 step 1 walk (#420), CRC lab; written by scripts/run.sh"; echo "# started $(now); kube context $(oc config current-context); merge ${merged}"; } > "${log}"
cleanup() { { printf '\n## exit trap  (%s)\n' "$(now)"; oc delete rolebindings.rbac.authorization.k8s.io,serviceaccounts -n ${ns} -l "${label}" --ignore-not-found 2>&1; } >> "${log}"; }
trap cleanup EXIT

note "Before"
run "oc get persistentvolumeclaims -n ${ns} -o custom-columns=NAME:.metadata.name,UID:.metadata.uid"
t0=$(date +%s)
until oc get applications.argoproj.io -n ${argo_ns} group-sync-dashboard -o jsonpath='{.status.sync.revision} {.status.sync.status} {.status.health.status}' | grep -qx "${merged} Synced Healthy"; do
  [ $(( $(date +%s) - t0 )) -ge 900 ] && { echo "NOT MET within 900 s: Argo CD synced ${merged}" >> "${log}"; exit 1; }; sleep 10; done
echo "Argo CD Synced/Healthy on ${merged} after $(( $(date +%s) - t0 )) s at $(now)" >> "${log}"
run "helm get metadata group-sync-dashboard -n ${ns} 2>/dev/null | grep -E '^(VERSION|APP_VERSION)' || oc get deployments.apps -n ${ns} group-sync-dashboard -o jsonpath='{.metadata.labels.helm\\.sh/chart}{\"\\n\"}'"

note "Step 1.2: the Role and RoleBinding"
run "oc get roles.rbac.authorization.k8s.io,rolebindings.rbac.authorization.k8s.io -n ${ns} group-sync-dashboard-leases -o name"
run "oc get roles.rbac.authorization.k8s.io -n ${ns} group-sync-dashboard-leases -o jsonpath='{.rules}'; echo"
run "oc get rolebindings.rbac.authorization.k8s.io -n ${ns} group-sync-dashboard-leases -o jsonpath='{.roleRef} {.subjects}'; echo"

note "Step 1.3: nothing narrowed (the ClusterRole still grants it outside the namespace)"
run "oc get clusterroles.rbac.authorization.k8s.io group-sync-dashboard-reader -o json | jq -c '[.rules[] | select((.resources // []) | index(\"leases\"))]'"
canis "system:serviceaccount:${ns}:${sa}" default >> "${log}"
canis "system:serviceaccount:${ns}:${sa}" "${ns}" >> "${log}"

note "Step 1.4: the Leases renew, and no Lease error is logged"
run "oc get leases.coordination.k8s.io -n ${ns} -o custom-columns=NAME:.metadata.name,HOLDER:.spec.holderIdentity,RENEW:.spec.renewTime,TYPE:.metadata.labels.groupsync-dashboard\\.io/lease-type"
sleep 20
run "oc get leases.coordination.k8s.io -n ${ns} -o custom-columns=NAME:.metadata.name,HOLDER:.spec.holderIdentity,RENEW:.spec.renewTime,TYPE:.metadata.labels.groupsync-dashboard\\.io/lease-type"
run "oc get pods -n ${ns} -l app=group-sync-dashboard -o custom-columns=NAME:.metadata.name,START:.status.startTime"
run "oc logs -n ${ns} deploy/group-sync-dashboard -c dashboard | grep -cE 'forbidden reading lease|could not renew lease|lost leadership|fleet-state-unavailable' || true"

note "For the operator's condition: the Role alone grants the three verbs in the namespace, and nothing outside it"
run "oc create serviceaccount g4-role-probe -n ${ns} && oc label serviceaccount g4-role-probe -n ${ns} ${label/=/=} --overwrite"
run "oc create rolebinding g4-role-probe -n ${ns} --role=group-sync-dashboard-leases --serviceaccount=${ns}:g4-role-probe && oc label rolebinding g4-role-probe -n ${ns} ${label/=/=} --overwrite"
sleep 3
canis "system:serviceaccount:${ns}:g4-role-probe" "${ns}" >> "${log}"
canis "system:serviceaccount:${ns}:g4-role-probe" default >> "${log}"
run "oc delete rolebindings.rbac.authorization.k8s.io,serviceaccounts -n ${ns} -l ${label}"

note "After"
run "oc get persistentvolumeclaims -n ${ns} -o custom-columns=NAME:.metadata.name,UID:.metadata.uid"
echo "walk done at $(now)" >> "${log}"
