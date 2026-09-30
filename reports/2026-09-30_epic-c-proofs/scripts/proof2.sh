#!/usr/bin/env bash
# PROOF 2 — #285's fleet-account row on the Cluster Configurations tab (after
# reports/2026-09-30_release-2.0.0-walk/scripts/run.sh): the exit trap, `can-i` before, the grant, 70 s for the tier's
# cache, `can-i` during, rows.py at 1280 and 375 px, the grant's delete, `can-i` and the label check after. The grant
# window (create to delete) is written to evidence/grant-window.txt in seconds.
#   GSD_WALK_TMP=<a directory outside the repo> KUBECONFIG=<the lab kubeconfig> scripts/proof2.sh
# developer's UI password is read from `crc console --credentials` into the walker's environment only, never printed.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
s="${here}/scripts"; ev="${here}/evidence"
ns=group-sync-dashboard
label=walk.gsd.lab/run=epic-c-proofs-2026-09-30
py=/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/.venv/bin/python
: "${GSD_WALK_TMP:?}"; : "${KUBECONFIG:?}"
export GSD_WALK_TMP KUBECONFIG PYTHONDONTWRITEBYTECODE=1
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
pw() { crc console --credentials -o json | jq -r .clusterConfig.developerCredentials.password; }
label_check() {
  { echo "# oc get secret,clusterrole,clusterrolebinding -A -l ${label}  (at $(now))"
    oc get secret,clusterrole,clusterrolebinding -A -l "${label}" 2>&1; } > "${ev}/$1-label-check.txt"
}
stamp() { echo "$(now) $*" >> "${ev}/p2-timeline.txt"; }

cleanup() {  # everything carrying the walk's label, whatever state the run stopped in
  { echo "# trap at $(now)"
    oc delete clusterrolebindings.rbac.authorization.k8s.io,clusterroles.rbac.authorization.k8s.io -l "${label}" --ignore-not-found
    oc delete secrets -n "${ns}" -l "${label}" --ignore-not-found
  } > "${ev}/p2-trap-delete.txt" 2>&1
}
trap cleanup EXIT

: > "${ev}/p2-timeline.txt"; : > "${ev}/mask-log.jsonl"
stamp "proof 2 start"
"${s}/capture.sh" cani p2-before
label_check p2-before

rc=0
{ echo "# oc create -f scripts/grant.yaml at $(now)"; oc create -f "${s}/grant.yaml"; } > "${ev}/p2-grant-create.txt" 2>&1
granted=$(date +%s); stamp "grant created"
"${s}/capture.sh" grant p2-during
left=$(( 70 - ($(date +%s) - granted) )); [ "${left}" -gt 0 ] && sleep "${left}"
"${s}/capture.sh" cani p2-during

stamp "rows.py"
GSD_UI_PASSWORD="$(pw)" "${py}" "${s}/rows.py" > "${ev}/p2-rows.txt" 2>&1 || rc=$?

{ echo "# delete the grant at $(now)"; oc delete -f "${s}/grant.yaml"; } > "${ev}/p2-delete-grant.txt" 2>&1
deleted=$(date +%s); stamp "grant deleted"
echo "grant created $(date -u -r "${granted}" +%Y-%m-%dT%H:%M:%SZ), deleted $(date -u -r "${deleted}" +%Y-%m-%dT%H:%M:%SZ): $(( deleted - granted )) s" \
  > "${ev}/grant-window.txt"
"${s}/capture.sh" cani p2-after
"${s}/capture.sh" grant p2-after
label_check p2-after
stamp "proof 2 end rc=${rc}"
echo "rows.py exit=${rc}" > "${ev}/p2-exit.txt"
exit "${rc}"
