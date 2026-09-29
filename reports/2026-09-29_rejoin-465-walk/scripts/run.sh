#!/usr/bin/env bash
# The #465 walk end to end. The exit trap deletes everything carrying the walk's label and is set BEFORE anything is
# created; the walk also deletes explicitly at the end (the trap's second pass then finds nothing, evidence/trap-delete.txt).
#   KUBECONFIG=<the lab kubeconfig> reports/2026-09-29_rejoin-465-walk/scripts/run.sh
# PY names a Python with Playwright (default: the main checkout's venv). The UI password is read from `crc console`
# into walk.py's environment only; it is never an argument and never printed.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
s="${here}/scripts"; e="${here}/evidence"
ns=group-sync-dashboard
run_label=walk.gsd.lab/run=rejoin-465-2026-09-29
PY="${PY:-/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/.venv/bin/python}"
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
say() { printf '%s %s\n' "$(now)" "$*"; }

# shellcheck disable=SC2329  # invoked by the EXIT trap
cleanup() {
  { printf '# exit trap: oc delete everything labelled %s\n# at %s\n' "${run_label}" "$(now)"
    oc delete secrets -n "${ns}" -l "${run_label}" --ignore-not-found 2>&1
    oc delete clusterrolebindings.rbac.authorization.k8s.io,clusterroles.rbac.authorization.k8s.io -l "${run_label}" \
      --ignore-not-found 2>&1; } >> "${e}/trap-delete.txt"
}
trap cleanup EXIT

T0=$(now); echo "${T0}" > "${e}/start-instant.txt"; say "the walk began: ${T0}"
for k in version pvcs sharedqa lease tokens cani grant secret; do "${s}/capture.sh" "${k}" before; done

"${s}/lab.sh" secret
# discovery adds w465 and its first poll answers auth_failed (the bogus token): at most 180 s
pod=$(oc get pods -n "${ns}" -l app.kubernetes.io/name=group-sync-dashboard -o jsonpath='{.items[0].metadata.name}')
for _ in $(seq 36); do
  if oc logs -n "${ns}" "${pod}" -c dashboard --since-time="${T0}" | grep -E 'w465' | grep -q 'auth_failed'; then break; fi
  sleep 5
done
say "w465 polled: $(oc logs -n "${ns}" "${pod}" -c dashboard --since-time="${T0}" | grep -E 'w465' | grep -c 'auth_failed' || true) auth_failed line(s)"
"${s}/capture.sh" secret during

"${s}/lab.sh" grant
"${s}/capture.sh" cani during; "${s}/capture.sh" grant during
say "waiting 70 s after the grant for the tier cache"; sleep 70

set +e
GSD_WALK_T0="${T0}" GSD_UI_PASSWORD="$(crc console --credentials -o json | jq -r .clusterConfig.developerCredentials.password)" \
  "${PY}" "${s}/walk.py" 2>&1 | tee "${e}/walk-output.txt"
walk_rc=${PIPESTATUS[0]}
set -e
say "walk.py exited ${walk_rc}"

for k in lease tokens; do "${s}/capture.sh" "${k}" during; done
"${s}/capture.sh" podlog walk "${T0}"

"${s}/lab.sh" delete
say "deleted by label at $(now)"
for _ in $(seq 36); do
  if oc logs -n "${ns}" "${pod}" -c dashboard --since-time="${T0}" | grep -E ' discovery ' | grep -q 'removed=w465'; then break; fi
  sleep 5
done
say "discovery removed w465: $(oc logs -n "${ns}" "${pod}" -c dashboard --since-time="${T0}" | grep ' discovery ' | grep -c 'removed=w465' || true) line(s)"
for k in cani grant secret version pvcs sharedqa lease tokens; do "${s}/capture.sh" "${k}" after; done
"${s}/capture.sh" audit after "${T0}"
"${s}/capture.sh" podlog after "${T0}"
say "done; walk.py exit ${walk_rc}"
exit "${walk_rc}"
