#!/usr/bin/env bash
# The Epic G release (application 4.0.0, chart 0.66.4) deployed and walked on the CRC lab, by the epic skill's close:
# `release-crc.sh --argocd main` (the published chart and images), then read-only checks: health, version, schema,
# the PVC UIDs, and one live check per feature this release carries (G1-G4, #542, #532).
#   KUBECONFIG=<the lab kubeconfig> scripts/run.sh <the release merge sha>
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"; log="${here}/walk.log"; repo="$(cd "${here}/../.." && pwd)"
ns=group-sync-dashboard; argo_ns=openshift-gitops; merged="${1:?the release merge sha}"
: "${KUBECONFIG:?}"; export KUBECONFIG
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
note() { printf '\n## %s  (%s)\n' "$*" "$(now)" >> "${log}"; }
run() { printf '$ %s\n' "$*" >> "${log}"; bash -c "$*" >> "${log}" 2>&1 || echo "(exit ${PIPESTATUS[0]})" >> "${log}"; }
as() { printf '%s' "oc exec -n ${ns} deploy/group-sync-dashboard -c dashboard -- curl -s -H 'X-Forwarded-User: $1' 'http://127.0.0.1:8080$2'"; }
host() { oc get routes.route.openshift.io -n ${ns} group-sync-dashboard -o jsonpath='{.status.ingress[0].host}'; }
{ echo "# Release 4.0.0 walk (Epic G #387), CRC lab; written by scripts/run.sh"; echo "# started $(now); kube context $(oc config current-context); merge ${merged}"; } > "${log}"

note "Before"
run "oc get persistentvolumeclaims -n ${ns} -o custom-columns=NAME:.metadata.name,UID:.metadata.uid"
run "oc get applications.argoproj.io -n ${argo_ns} group-sync-dashboard -o json | jq -c '{rev: .spec.source.targetRevision, sync: .status.sync.status, health: .status.health.status, synced: .status.sync.revision, cond: [.status.conditions[]?.type]}'"

note "Deploy: release-crc.sh --argocd main (the published release)"
run "cd '${repo}' && timeout 1200 local-development/release-crc.sh --argocd main --values environments/crc.yaml 2>&1 | grep -vE 'status is for the previous spec' | tail -12"
t0=$(date +%s)
until oc get applications.argoproj.io -n ${argo_ns} group-sync-dashboard -o jsonpath='{.status.sync.revision} {.status.sync.status} {.status.health.status}' | grep -qx "${merged} Synced Healthy" \
      && oc exec -n ${ns} deploy/group-sync-dashboard -c dashboard -- curl -s http://127.0.0.1:8080/api/version | jq -e '.version == "4.0.0"' > /dev/null 2>&1; do
  [ $(( $(date +%s) - t0 )) -ge 900 ] && { echo "NOT MET within 900 s: 4.0.0 Synced/Healthy" >> "${log}"; exit 1; }; sleep 10; done
echo "4.0.0 Synced/Healthy on ${merged} at $(now)" >> "${log}"
run "oc get applications.argoproj.io -n ${argo_ns} group-sync-dashboard -o json | jq -c '{sync: .status.sync.status, health: .status.health.status, synced: .status.sync.revision, op: .status.operationState.phase, retries: .status.operationState.retryCount}'"
run "oc get deployments.apps -n ${ns} -o 'custom-columns=NAME:.metadata.name,WANT:.spec.replicas,READY:.status.readyReplicas,IMAGE:.spec.template.spec.containers[0].image' | grep -E 'NAME|group-sync-dashboard'"

note "Health, version, schema"
run "for p in /healthz /readyz; do printf '%s ' \$p; curl -sk -w ' %{http_code}\n' https://\$(oc get routes.route.openshift.io -n ${ns} group-sync-dashboard -o jsonpath='{.status.ingress[0].host}')\$p; done"
run "curl -sk https://\$(oc get routes.route.openshift.io -n ${ns} group-sync-dashboard -o jsonpath='{.status.ingress[0].host}')/metrics | grep -E '^gsd_build_info'"
run "oc exec -n ${ns} deploy/group-sync-dashboard -c dashboard -- python3.14 -c \"import sqlite3; print('user_version', sqlite3.connect('file:/data/gsd.db?mode=ro', uri=True).execute('PRAGMA user_version').fetchone()[0])\""
run "oc exec -n ${ns} deploy/group-sync-dashboard -c dashboard -- python3.14 -c 'import gsd.store as s; print(\"image migrations\", len(s._MIGRATIONS))'"

note "One live check per feature"
run "echo 'G1 (#239): a route the declaration gates at the cluster-admin tier refuses the self tier'; $(as developer /api/housekeeping/copies) | jq -c '{detail}'"
run "echo 'G2 (#255) and G3 (#503), as dana.lee'; $(as dana.lee /api/clusters/dashboard/user-bindings) | jq -c '{scope, total, excluded_platform, platform_users_unmatched, acknowledged, acknowledged_sources: [(.acknowledged_bindings // [])[] | .managed_source] | unique}'"
run "echo 'G4 (#420)'; oc get clusterroles.rbac.authorization.k8s.io group-sync-dashboard-reader -o json | jq -c '[.rules[] | select((.resources // []) | index(\"leases\"))] | length'; oc get roles.rbac.authorization.k8s.io group-sync-dashboard-leases -n ${ns} -o jsonpath='{.rules}'; echo; oc get leases.coordination.k8s.io group-sync-dashboard -n ${ns} -o jsonpath='{.spec.holderIdentity} {.spec.renewTime} {.spec.leaseTransitions}'; echo"
run "echo '#542'; oc exec -n ${ns} deploy/group-sync-dashboard -c dashboard -- curl -s http://127.0.0.1:8080/api/version | jq -c '.features'"
run "echo '#532'; oc get deployments.apps -n ${ns} group-sync-dashboard-recovery -o jsonpath='{.spec.replicas}/{.status.readyReplicas}'; echo"

note "After"
run "oc get persistentvolumeclaims -n ${ns} -o custom-columns=NAME:.metadata.name,UID:.metadata.uid"
echo "walk done at $(now)" >> "${log}"
