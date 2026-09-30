#!/usr/bin/env bash
# The #492 walk end to end (cut down from reports/2026-09-29_ca-244-walk/scripts/run.sh): before-captures, the exit
# trap, walk.py precheck (no grant), the CA, the throwaway Secret and the grant, the waits (discovery, the first poll,
# 70 s after the grant), walk.py live (1280 px, then 375 px), the Secret's delete, the wait for discovery to retire
# it, walk.py retired, the grant's delete, then the after-captures and the final label check.
#   GSD_WALK_TMP=<a directory outside the repo> KUBECONFIG=<the lab kubeconfig> scripts/run.sh
# developer's UI password is read from `crc console --credentials` into walk.py's environment only, never printed.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
s="${here}/scripts"; ev="${here}/evidence"
ns=group-sync-dashboard
label=walk.gsd.lab/run=chip-492-2026-09-30
py=/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/.venv/bin/python
: "${GSD_WALK_TMP:?}"; : "${KUBECONFIG:?}"
export GSD_WALK_TMP KUBECONFIG
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log_since() { oc logs -n "${ns}" deploy/group-sync-dashboard -c dashboard --timestamps --since-time="$1"; }
# wait_for <evidence name> <seconds> <extended regex> ...: every regex must match a line of the log since t0
wait_for() {
  local name="$1" limit="$2"; shift 2
  local start; start=$(date +%s)
  while :; do
    local logtext missing=0; logtext=$(log_since "${t0}")
    for re in "$@"; do grep -qE -- "${re}" <<< "${logtext}" || missing=1; done
    if [ "${missing}" = 0 ]; then
      { echo "# waited $(( $(date +%s) - start )) s, until $(now), for: $*"
        for re in "$@"; do grep -E -- "${re}" <<< "${logtext}" | head -3 | sed -E 's/sha256~[A-Za-z0-9_-]+/sha256~<redacted>/g'; done
      } > "${ev}/wait-${name}.txt"
      return 0
    fi
    if [ $(( $(date +%s) - start )) -ge "${limit}" ]; then
      echo "# gave up after ${limit} s at $(now), waiting for: $*" > "${ev}/wait-${name}.txt"; return 1
    fi
    sleep 10
  done
}
walk() {  # walk.py <mode>, its output in evidence/walk-<mode>.txt; the password only in its environment
  GSD_UI_PASSWORD="$(crc console --credentials -o json | jq -r .clusterConfig.developerCredentials.password)" \
    "${py}" "${s}/walk.py" "$1" > "${ev}/walk-$1.txt" 2>&1
}
label_check() {
  { echo "# oc get secret,clusterrole,clusterrolebinding -A -l ${label}  (at $(now))"
    oc get secret,clusterrole,clusterrolebinding -A -l "${label}" 2>&1; } > "${ev}/$1-label-check.txt"
}

t0=$(now); echo "${t0}" > "${ev}/start-instant.txt"
for k in version pod pvcs sharedqa lease cani grant secrets; do "${s}/capture.sh" "${k}" before; done
label_check before

cleanup() {  # everything carrying the walk's label, whatever state the run stopped in
  { echo "# trap at $(now)"
    oc delete secrets -n "${ns}" -l "${label}" --ignore-not-found
    oc delete clusterrolebindings.rbac.authorization.k8s.io,clusterroles.rbac.authorization.k8s.io -l "${label}" --ignore-not-found
  } > "${ev}/trap-delete.txt" 2>&1
}
trap cleanup EXIT

rc=0
walk precheck || rc=$?

"${s}/secrets.sh" ca > "${ev}/generated-ca.txt"
{ echo "# at $(now)"; "${s}/secrets.sh" create; } > "${ev}/secret-create.txt" 2>&1
{ echo "# oc create -f scripts/grant.yaml at $(now)"; oc create -f "${s}/grant.yaml"; } > "${ev}/grant-create.txt" 2>&1
granted=$(date +%s)
"${s}/capture.sh" walksecrets during
"${s}/capture.sh" grant during

wait_for discovery-added 400 'discovery cycle=[0-9]+ .*added=[^ ]*w492-fail'
wait_for first-poll 180 'outcome=cert-verify-failed .*cluster=w492-fail '
left=$(( 70 - ($(date +%s) - granted) )); [ "${left}" -gt 0 ] && sleep "${left}"
"${s}/capture.sh" cani during

walk live || rc=$?

{ echo "# delete the Secret at $(now)"; "${s}/secrets.sh" delete; } > "${ev}/delete-secret.txt" 2>&1
wait_for discovery-removed 400 'discovery cycle=[0-9]+ .*removed=[^ ]*w492-fail' || rc=$?
walk retired || rc=$?

{ echo "# delete the grant at $(now)"; oc delete -f "${s}/grant.yaml"; } > "${ev}/delete-grant.txt" 2>&1
for k in cani grant secrets version pod pvcs sharedqa lease; do "${s}/capture.sh" "${k}" after; done
"${s}/capture.sh" podlog after "${t0}"
label_check after
echo "walk exit=${rc}" > "${ev}/run-exit.txt"
exit "${rc}"
