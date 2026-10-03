#!/usr/bin/env bash
# SPEC_G4 §5 step 2 (#420) on the CRC lab: the ClusterRole's Lease rule removed (chart 0.66.3). Argo CD auto-syncs
# main, so this runs BEFORE the merge: it arms the T420-8 recorders, waits for the Application to sync a revision past
# <main before the merge> with the rule gone, keeps recording a minute more, then reads T420-7 and the logs.
#   KUBECONFIG=<the lab kubeconfig> scripts/run.sh <main before #562's merge>
# Recorders: renew-trace.log (the elector Lease's holder, renewTime and leaseTransitions every 2 s) and
# old-pod-follow.log (`oc logs -f` of the dashboard container that is running when the walk starts). Read-only on the
# cluster: nothing here writes.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"; log="${here}/walk.log"
ns=group-sync-dashboard; sa="system:serviceaccount:group-sync-dashboard:group-sync-dashboard"; argo_ns=openshift-gitops
before="${1:?the main sha before the merge of #562}"
: "${KUBECONFIG:?}"; export KUBECONFIG
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
note() { printf '\n## %s  (%s)\n' "$*" "$(now)" >> "${log}"; }
run() { printf '$ %s\n' "$*" >> "${log}"; bash -c "$*" >> "${log}" 2>&1 || echo "(exit ${PIPESTATUS[0]})" >> "${log}"; }
{ echo "# SPEC_G4 §5 step 2 walk (#420), CRC lab; written by scripts/run.sh"; echo "# started $(now); kube context $(oc config current-context); main before the merge ${before}"; } > "${log}"

note "Before"
run "oc get persistentvolumeclaims -n ${ns} -o custom-columns=NAME:.metadata.name,UID:.metadata.uid"
run "oc get roles.rbac.authorization.k8s.io group-sync-dashboard-leases -n ${ns} -o name"
run "oc get clusterroles.rbac.authorization.k8s.io group-sync-dashboard-reader -o json | jq -c '[.rules[] | select((.resources // []) | index(\"leases\"))]'"
old=$(oc get pods -n ${ns} -l app=group-sync-dashboard -o jsonpath='{.items[0].metadata.name}')
echo "the running pod: ${old}" >> "${log}"

note "The T420-8 recorders"
( while :; do printf '%s %s\n' "$(now)" "$(oc get leases.coordination.k8s.io group-sync-dashboard -n ${ns} -o jsonpath='{.spec.holderIdentity} {.spec.renewTime} {.spec.leaseTransitions}' 2>&1)"; sleep 2; done ) > "${here}/renew-trace.log" &
tracer=$!
oc logs -f -n ${ns} "${old}" -c dashboard --since=1s > "${here}/old-pod-follow.log" 2>&1 &
follower=$!
trap 'kill ${tracer} ${follower} 2>/dev/null || true' EXIT
echo "recorders armed at $(now)" >> "${log}"

note "Waiting for the merge to sync (the rule gone from the ClusterRole)"
t0=$(date +%s)
until rev=$(oc get applications.argoproj.io -n ${argo_ns} group-sync-dashboard -o jsonpath='{.status.sync.revision} {.status.sync.status} {.status.health.status}') \
      && [ "${rev%% *}" != "${before}" ] && [ "${rev#* }" = "Synced Healthy" ] \
      && [ "$(oc get clusterroles.rbac.authorization.k8s.io group-sync-dashboard-reader -o json | jq '[.rules[] | select((.resources // []) | index("leases"))] | length')" = 0 ]; do
  [ $(( $(date +%s) - t0 )) -ge 5400 ] && { echo "NOT MET within 5400 s: the narrowing deployed" >> "${log}"; exit 1; }; sleep 10; done
echo "synced ${rev} with no Lease rule in the ClusterRole, $(( $(date +%s) - t0 )) s after arming, at $(now)" >> "${log}"
run "oc rollout status -n ${ns} deploy/group-sync-dashboard --timeout=10m"
sleep 60; echo "recorded 60 s more, until $(now)" >> "${log}"
kill "${tracer}" "${follower}" 2>/dev/null || true

note "T420-8: the trace and the logs"
run "awk '{print \$2, \$4}' '${here}/renew-trace.log' | uniq -c | tail -12"
run "awk '{print \$2}' '${here}/renew-trace.log' | sort -u"
new=$(oc get pods -n ${ns} -l app=group-sync-dashboard -o jsonpath='{.items[0].metadata.name}')
echo "the new pod: ${new} (the old: ${old})" >> "${log}"
run "grep -cE 'forbidden reading lease|could not renew lease|lost leadership|fleet-state-unavailable' '${here}/old-pod-follow.log' || true"
run "oc logs -n ${ns} ${new} -c dashboard | grep -cE 'forbidden reading lease|could not renew lease|lost leadership|fleet-state-unavailable' || true"
run "oc logs -n ${ns} ${new} -c dashboard | grep -iE 'lease|leader' | head -5"

note "T420-7: the narrowing"
run "oc get clusterroles.rbac.authorization.k8s.io group-sync-dashboard-reader -o jsonpath='{.rules[*].resources}'; echo"
for n in default kube-system kube-node-lease openshift-kube-controller-manager openshift-kube-scheduler group-sync-dashboard; do
  for v in get create update; do printf '%s %s in %s: %s\n' "${sa##*:}" "${v}" "${n}" "$(oc auth can-i "${v}" leases.coordination.k8s.io --as "${sa}" -n "${n}" 2>/dev/null || true)"; done
done >> "${log}"

note "After"
run "oc get leases.coordination.k8s.io -n ${ns} -o custom-columns=NAME:.metadata.name,HOLDER:.spec.holderIdentity,RENEW:.spec.renewTime"
run "oc get persistentvolumeclaims -n ${ns} -o custom-columns=NAME:.metadata.name,UID:.metadata.uid"
echo "walk done at $(now)" >> "${log}"
