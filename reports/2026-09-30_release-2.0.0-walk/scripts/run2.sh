#!/usr/bin/env bash
# The second, short grant window: the KPIs and Cluster Configurations tabs captured once painted (tabs_loaded.py),
# because run.sh's e2e pass photographed both while they read `Loading…`. The same grant, trap, 70 s wait and
# can-i checks as run.sh; captures are labelled p2-*.
#   GSD_WALK_TMP=<a directory outside the repo> KUBECONFIG=<the lab kubeconfig> scripts/run2.sh
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
s="${here}/scripts"; ev="${here}/evidence"
ns=group-sync-dashboard
label=walk.gsd.lab/run=release-200-2026-09-30
py=/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/.venv/bin/python
: "${GSD_WALK_TMP:?}"; : "${KUBECONFIG:?}"
export GSD_WALK_TMP KUBECONFIG PYTHONDONTWRITEBYTECODE=1
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
pw() { crc console --credentials -o json | jq -r .clusterConfig.developerCredentials.password; }
label_check() {
  { echo "# oc get secret,clusterrole,clusterrolebinding -A -l ${label}  (at $(now))"
    oc get secret,clusterrole,clusterrolebinding -A -l "${label}" 2>&1; } > "${ev}/$1-label-check.txt"
}
stamp() { echo "$(now) $*" >> "${ev}/timeline.txt"; }

t0=$(now)
stamp "second window start"
for k in version cani grant secrets pvcs sharedqa lease; do "${s}/capture.sh" "${k}" p2-before; done
label_check p2-before

cleanup() {
  { echo "# trap at $(now)"
    oc delete clusterrolebindings.rbac.authorization.k8s.io,clusterroles.rbac.authorization.k8s.io -l "${label}" --ignore-not-found
    oc delete secrets -n "${ns}" -l "${label}" --ignore-not-found
  } > "${ev}/p2-trap-delete.txt" 2>&1
}
trap cleanup EXIT

rc=0
{ echo "# oc create -f scripts/grant.yaml at $(now)"; oc create -f "${s}/grant.yaml"; } > "${ev}/p2-grant-create.txt" 2>&1
granted=$(date +%s); stamp "second grant created"
"${s}/capture.sh" grant p2-during
left=$(( 70 - ($(date +%s) - granted) )); [ "${left}" -gt 0 ] && sleep "${left}"
"${s}/capture.sh" cani p2-during

stamp "tabs_loaded.py"
( cd "${s}" && GSD_UI_PASSWORD="$(pw)" "${py}" tabs_loaded.py ) > "${ev}/walk-tabs-painted.txt" 2>&1 || rc=$?

{ echo "# delete the grant at $(now)"; oc delete -f "${s}/grant.yaml"; } > "${ev}/p2-delete-grant.txt" 2>&1
stamp "second grant deleted"
for k in cani grant secrets version pvcs sharedqa lease argo; do "${s}/capture.sh" "${k}" p2-after; done
"${s}/capture.sh" podlog p2-after "${t0}"
label_check p2-after
stamp "second window end rc=${rc}"
echo "walk exit=${rc}" > "${ev}/p2-run-exit.txt"
exit "${rc}"
