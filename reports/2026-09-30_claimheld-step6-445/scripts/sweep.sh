#!/usr/bin/env bash
# #445's restore: scripts/run.sh's EXIT trap, and its hand-back. reports/2026-09-30_selflogin-renewal-310/scripts/
# sweep.sh less the oauth/cluster step and `developer`'s ClusterRoleBinding (this walk makes neither), with a guard
# on `developer`'s Lease that the #310 walk did not need (this walk's own processes hold it). Safe to run any number
# of times — each step reads the state first and does nothing when it is already where it should be.
#   1. The walk Secret, by the run label. The walk never creates it; the step proves it absent.
#   2. The ServiceAccount's keep-grant, by the run label — ONLY when the chart's own group-sync-dashboard-fleet-account
#      Role in openshift-config grants `get` on ldap-oauth-bind-secret again (after `release-crc.sh --argocd main`)
#      AND the lab is on Argo CD (lib.sh#on_argo: a cascade cut short still shows that Role while deleting it).
#      Before that the grant is the only thing holding that permission, and it stays: the dashboard ServiceAccount's
#      permissions never drop (the operator's rule of 2026-09-25).
#   3. `developer`'s Lease, by name — ONLY when the deployed configuration names no `developer` account AND no live
#      claim holds it. Step 6's process A created it (it was absent at the start: run.sh's preflight); it carries no
#      run label. A live holder is a coordinator still running or one killed within the claim's duration: the spec
#      says wait for it, never delete it (SPEC_S4c §3.12 step 6.1-6.3, "Do not delete the Lease").
# Usage: sweep.sh <label>   -> appended to evidence/<label>-sweep.txt, and the same on stdout.
# Exit 0 when everything is removed; 5 when something was deliberately left (the line says what and why);
# otherwise 1.
set -uo pipefail
label="${1:?label}"
# shellcheck source-path=SCRIPTDIR source=lib.sh
. "$(dirname "$0")/lib.sh"
out="${EVIDENCE}/${label}-sweep.txt"
left=0; rc=0

{
  say "sweep '${label}' begins"

  # 1. The walk Secret: never created; deleted by label if it somehow exists, then proved absent by name.
  say "1. $(oc delete secrets -n "${NS}" -l "${RUN_LABEL}" --ignore-not-found 2>&1 | tr '\n' ' ')(the walk Secret, by label)"
  [ -z "$(oc get secrets -n "${NS}" "${WALK_SECRET}" -o name --ignore-not-found)" ] || { say "1. FAILED: ${WALK_SECRET} exists"; rc=1; }

  # 2. The keep-grant, only once the chart's own grant is back.
  chart_role=$(oc get roles.rbac.authorization.k8s.io -n openshift-config group-sync-dashboard-fleet-account -o json 2>/dev/null \
    | jq -r '[.rules[] | select((.resources | index("secrets")) and (.verbs | index("get")) and ((.resourceNames // []) | index("ldap-oauth-bind-secret")))] | length' 2>/dev/null || echo 0)
  chart_binding=$(oc get rolebindings.rbac.authorization.k8s.io -n openshift-config -o json 2>/dev/null \
    | jq -r --arg ns "${NS}" '[.items[] | select(.roleRef.kind == "Role" and .roleRef.name == "group-sync-dashboard-fleet-account")
         | .subjects[]? | select(.kind == "ServiceAccount" and .name == "group-sync-dashboard" and .namespace == $ns)] | length' 2>/dev/null || echo 0)
  # The chart's grant counts only on a lab that is on Argo CD: while a cut-short cascade is deleting the Application,
  # the Role is still readable and about to go (lib.sh#on_argo).
  argo=no; on_argo && argo=yes
  if [ -z "$(oc get roles.rbac.authorization.k8s.io -n openshift-config -l "${RUN_LABEL}" -o name)" ]; then
    say "2. no keep-grant present"
  elif [ "${chart_role:-0}" -ge 1 ] && [ "${chart_binding:-0}" -ge 1 ] && [ "${argo}" = yes ]; then
    say "2. the chart's group-sync-dashboard-fleet-account Role and binding grant the ServiceAccount get on ldap-oauth-bind-secret: removing the keep-grant"
    say "2. $(oc delete roles.rbac.authorization.k8s.io,rolebindings.rbac.authorization.k8s.io -n openshift-config -l "${RUN_LABEL}" --ignore-not-found 2>&1 | tr '\n' ' ')"
  else
    say "2. LEFT: the keep-grant stays — the chart's own grant on ldap-oauth-bind-secret is not back on a lab that is on Argo CD (Role rules matching: ${chart_role:-0}, bindings: ${chart_binding:-0}, on Argo CD: ${argo}). Run release-crc.sh --argocd main, then this script again."
    left=1
  fi

  # 3. developer's Lease, only once nothing configured names developer and no live claim holds it.
  if ! state=$(dev_lease_state); then
    say "3. FAILED: ${DEV_LEASE} could not be read"; rc=1
  elif [ "${state}" = absent ]; then
    say "3. ${DEV_LEASE} is absent"
  else
    named=$(oc get configmaps -n "${NS}" group-sync-dashboard-config -o json | jq -r '.data["clusters.yaml"]' \
      | grep -c -E '^fleetAccountUsername: "?developer"?$|ldapConnectionBootstrap: "?developer"?$' || true)
    if [ "${named}" != 0 ]; then
      say "3. LEFT: ${DEV_LEASE} stays — the deployed configuration still names developer (${named} line(s)). Run release-crc.sh --argocd main, then this script again."
      left=1
    elif ! dev_lease_free; then
      say "3. LEFT: ${DEV_LEASE} stays — a live claim holds it (${state}); wait until renew + duration has passed, then run this script again."
      left=1
    else
      say "3. the deployed configuration names no developer account and no claim holds it (${state}): $(oc delete leases.coordination.k8s.io -n "${NS}" "${DEV_LEASE}" --ignore-not-found 2>&1 | tr '\n' ' ')"
    fi
  fi

  say "labelled ${RUN_LABEL} now: $(oc get secrets,roles.rbac.authorization.k8s.io,rolebindings.rbac.authorization.k8s.io -A -l "${RUN_LABEL}" -o name | tr '\n' ' ')$(oc get clusterrolebindings.rbac.authorization.k8s.io -l "${RUN_LABEL}" -o name | tr '\n' ' ')"
  say "sweep '${label}' ends: rc=${rc} left=${left}"
} 2>&1 | tee -a "${out}"
# The group ran in a pipeline's subshell: re-derive the outcome from what it wrote.
tail -1 "${out}" | grep -q 'rc=0 left=0' && exit 0
tail -1 "${out}" | grep -q 'rc=0 left=1' && exit 5
exit 1
