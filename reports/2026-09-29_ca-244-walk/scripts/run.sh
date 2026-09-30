#!/usr/bin/env bash
# The #244 walk end to end: before-captures, the exit trap, two CAs, two throwaway Secrets and the grant, the waits
# (discovery, both first polls, 70 s after the grant), walk.py, the byte-for-byte comparisons, the explicit delete,
# the after-captures, then the wait for discovery to retire the two entries and the end-captures.
#   GSD_WALK_TMP=<a directory outside the repo> KUBECONFIG=<the lab kubeconfig> scripts/run.sh
# developer's UI password is read from `crc console --credentials` into walk.py's environment only, never printed.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
s="${here}/scripts"; ev="${here}/evidence"
ns=group-sync-dashboard
label=walk.gsd.lab/run=ca-244-2026-09-29
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

t0=$(now); echo "${t0}" > "${ev}/start-instant.txt"
for k in version pvcs sharedqa lease cani grant secrets; do "${s}/capture.sh" "${k}" before; done

cleanup() {  # everything carrying the walk's label, whatever state the run stopped in
  { echo "# trap at $(now)"
    oc delete secrets -n "${ns}" -l "${label}" --ignore-not-found
    oc delete clusterrolebindings.rbac.authorization.k8s.io,clusterroles.rbac.authorization.k8s.io -l "${label}" --ignore-not-found
  } > "${ev}/trap-delete.txt" 2>&1
}
trap cleanup EXIT

"${s}/secrets.sh" cas > "${ev}/generated-cas.txt"
{ echo "# at $(now)"; "${s}/secrets.sh" create; } > "${ev}/secret-create.txt" 2>&1
{ echo "# oc create -f scripts/grant.yaml at $(now)"; oc create -f "${s}/grant.yaml"; } > "${ev}/grant-create.txt" 2>&1
granted=$(date +%s)
"${s}/capture.sh" walksecrets during
"${s}/capture.sh" grant during

wait_for discovery-added 400 'discovery cycle=[0-9]+ .*added=[^ ]*w244-exp' 'discovery cycle=[0-9]+ .*added=[^ ]*w244-fail'
wait_for first-polls 180 'outcome=cert-verify-failed .*cluster=w244-fail ' 'outcome=cert-verify-failed .*cluster=w244-exp '
left=$(( 70 - ($(date +%s) - granted) )); [ "${left}" -gt 0 ] && sleep "${left}"
"${s}/capture.sh" cani during

rc=0
GSD_WALK_T0="${t0}" GSD_UI_PASSWORD="$(crc console --credentials -o json | jq -r .clusterConfig.developerCredentials.password)" \
  "${py}" "${s}/walk.py" > "${ev}/walk-output.txt" 2>&1 || rc=$?
{ for f in action store; do
    echo "# cmp evidence/C-${f}-api.txt evidence/C-${f}-log.txt"
    if cmp "${ev}/C-${f}-api.txt" "${ev}/C-${f}-log.txt"; then echo "identical: $(wc -c < "${ev}/C-${f}-api.txt" | tr -d ' ') bytes each"; fi
  done; } > "${ev}/C-cmp.txt" 2>&1 || true

{ echo "# explicit delete at $(now)"; "${s}/secrets.sh" delete; oc delete -f "${s}/grant.yaml"; } > "${ev}/delete.txt" 2>&1
for k in cani grant secrets version pvcs sharedqa lease; do "${s}/capture.sh" "${k}" after; done
"${s}/capture.sh" podlog after "${t0}"

wait_for discovery-removed 400 'discovery cycle=[0-9]+ .*removed=[^ ]*w244-exp' || true
for k in secrets version pvcs sharedqa lease cani grant; do "${s}/capture.sh" "${k}" end; done
"${s}/capture.sh" podlog end "${t0}"
"${s}/capture.sh" redaction end
echo "walk.py exit=${rc}" > "${ev}/run-exit.txt"
exit "${rc}"
