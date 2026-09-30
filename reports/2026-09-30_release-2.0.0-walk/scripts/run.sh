#!/usr/bin/env bash
# The release 2.0.0 walk end to end (after reports/2026-09-30_chip-492-walk/scripts/run.sh): the before-captures,
# the exit trap, epicd.py precheck (no grant), the grant, 70 s for the tier's cache, epicd.py live (Epic D on the
# Cluster Configurations tab, Refresh once on mock-privateca), the e2e walk's main pass and second pass through
# e2e_masked.py, the grant's delete, the after-captures, and then the steps that need no grant: the integrity check,
# the environment facts and the walk document.
#   GSD_WALK_TMP=<a directory outside the repo> KUBECONFIG=<the lab kubeconfig> scripts/run.sh
# developer's UI password is read from `crc console --credentials` into each walker's environment only, never printed.
# The e2e walk's raw output goes to $GSD_WALK_TMP/e2e; what is committed is copied from there afterwards.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
s="${here}/scripts"; ev="${here}/evidence"
repo="$(cd "${here}/../.." && pwd)"
ns=group-sync-dashboard
label=walk.gsd.lab/run=release-200-2026-09-30
base=https://group-sync-dashboard.apps-crc.testing
py=/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/.venv/bin/python
tools="${repo}/local-development/e2e-walk"
: "${GSD_WALK_TMP:?}"; : "${KUBECONFIG:?}"
export GSD_WALK_TMP KUBECONFIG PYTHONDONTWRITEBYTECODE=1
out="${GSD_WALK_TMP}/e2e"
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
pw() { crc console --credentials -o json | jq -r .clusterConfig.developerCredentials.password; }
label_check() {
  { echo "# oc get secret,clusterrole,clusterrolebinding -A -l ${label}  (at $(now))"
    oc get secret,clusterrole,clusterrolebinding -A -l "${label}" 2>&1; } > "${ev}/$1-label-check.txt"
}
stamp() { echo "$(now) $*" >> "${ev}/timeline.txt"; }

t0=$(now); echo "${t0}" > "${ev}/start-instant.txt"; : > "${ev}/timeline.txt"; : > "${ev}/mask-log.jsonl"
stamp "walk start"
for k in version pod chart argo cronjob pvcs sharedqa lease cani grant secrets; do "${s}/capture.sh" "${k}" before; done
label_check before

cleanup() {  # everything carrying the walk's label, whatever state the run stopped in
  { echo "# trap at $(now)"
    oc delete clusterrolebindings.rbac.authorization.k8s.io,clusterroles.rbac.authorization.k8s.io -l "${label}" --ignore-not-found
    oc delete secrets -n "${ns}" -l "${label}" --ignore-not-found
  } > "${ev}/trap-delete.txt" 2>&1
}
trap cleanup EXIT

rc=0
stamp "epicd.py precheck (no grant)"
GSD_UI_PASSWORD="$(pw)" "${py}" "${s}/epicd.py" precheck > "${ev}/walk-precheck.txt" 2>&1 || rc=$?

{ echo "# oc create -f scripts/grant.yaml at $(now)"; oc create -f "${s}/grant.yaml"; } > "${ev}/grant-create.txt" 2>&1
granted=$(date +%s); stamp "grant created"
"${s}/capture.sh" grant during
left=$(( 70 - ($(date +%s) - granted) )); [ "${left}" -gt 0 ] && sleep "${left}"
"${s}/capture.sh" cani during

stamp "epicd.py live"
GSD_UI_PASSWORD="$(pw)" "${py}" "${s}/epicd.py" live > "${ev}/walk-live.txt" 2>&1 || rc=$?

rm -rf "${out}"; mkdir -p "${out}"
stamp "e2e main walk"
GSD_UI_PASSWORD="$(pw)" "${py}" "${s}/e2e_masked.py" capture --base "${base}" --login-user developer \
  --provider developer --out "${out}" > "${ev}/e2e-main.txt" 2>&1 || rc=$?
stamp "e2e second pass"
GSD_UI_PASSWORD="$(pw)" "${py}" "${s}/e2e_masked.py" extra "${out}" --base "${base}" --login-user developer \
  --provider developer > "${ev}/e2e-extra.txt" 2>&1 || rc=$?

{ echo "# delete the grant at $(now)"; oc delete -f "${s}/grant.yaml"; } > "${ev}/delete-grant.txt" 2>&1
stamp "grant deleted"
for k in cani grant secrets version pod chart argo cronjob pvcs sharedqa lease; do "${s}/capture.sh" "${k}" after; done
"${s}/capture.sh" podlog after "${t0}"
label_check after

stamp "integrity, environment facts, document"
"${py}" "${tools}/integrity_check.py" "${out}" > "${ev}/integrity-check.txt" 2>&1 || rc=$?
"${tools}/env_facts.sh" "${ns}" group-sync-dashboard > "${out}/env.json" 2> "${ev}/env-facts-stderr.txt" || rc=$?
"${py}" "${tools}/build_doc.py" "${out}" "${out}/env.json" > "${ev}/build-doc.txt" 2>&1 || rc=$?
stamp "walk end rc=${rc}"
echo "walk exit=${rc}" > "${ev}/run-exit.txt"
exit "${rc}"
