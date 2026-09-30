#!/usr/bin/env bash
# #310 Part A's restore: scripts/run.sh's EXIT trap, and its hand-back. Safe to run any number of times — each step
# reads the state first and does nothing when it is already where it should be.
#   1. oauth/cluster's accessTokenMaxAgeSeconds back to 31536000, and nothing else in that object
#      (scripts/oauth_lifetime.sh: no patch when it already reads 31536000), with the authentication operator settled.
#   2. The walk Secret, by the run label: after it, nothing can present `developer`'s password.
#   3. `developer`'s ClusterRoleBinding, by the run label.
#   4. The ServiceAccount's keep-grant, by the run label — ONLY when the chart's own group-sync-dashboard-fleet-account
#      Role in openshift-config grants `get` on ldap-oauth-bind-secret again (after `release-crc.sh --argocd main`).
#      Before that the grant is the only thing holding that permission, and it stays: the dashboard ServiceAccount's
#      permissions never drop (the operator's rule of 2026-09-25).
#   5. `developer`'s Lease, by name — ONLY when the deployed configuration names no `developer` account, so no path
#      claims it again. The product made it; it carries no run label.
# Usage: sweep.sh <label>   -> appended to evidence/<label>-sweep.txt, and the same on stdout.
# Exit 0 when everything is removed and restored; 5 when something was deliberately left (the line says what and
# why); otherwise the failing step's code.
set -uo pipefail
label="${1:?label}"
# shellcheck source-path=SCRIPTDIR source=lib.sh
. "$(dirname "$0")/lib.sh"
here="$(dirname "$0")"
out="${EVIDENCE}/${label}-sweep.txt"
dev_lease="gsd-fleet-$(printf '%s' developer | shasum -a 256 | cut -c1-16)"
left=0; rc=0

{
  say "sweep '${label}' begins"

  # 1. The lifetime first: whatever else fails, the cluster-wide change is undone.
  bash "${here}/oauth_lifetime.sh" set "${LIFETIME_FOUND}" "${label}"; r=$?
  now_cfg=$(token_config)
  if [ "${r}" -eq 0 ] && [ "${now_cfg}" = "{\"accessTokenMaxAgeSeconds\":${LIFETIME_FOUND}}" ]; then
    say "1. oauth/cluster spec.tokenConfig is ${now_cfg}, the authentication operator settled"
  else
    say "1. FAILED: oauth_lifetime.sh exited ${r}; spec.tokenConfig reads ${now_cfg}"; rc=${r:-1}
  fi

  # 2. The walk Secret.
  say "2. $(oc delete secrets -n "${NS}" -l "${RUN_LABEL}" --ignore-not-found 2>&1 | tr '\n' ' ')(the walk Secret, by label)"
  [ -z "$(oc get secrets -n "${NS}" "${WALK_SECRET}" -o name --ignore-not-found)" ] || { say "2. FAILED: ${WALK_SECRET} is still there"; rc=2; }

  # 3. developer's grant.
  say "3. $(oc delete clusterrolebindings.rbac.authorization.k8s.io -l "${RUN_LABEL}" --ignore-not-found 2>&1 | tr '\n' ' ')(developer's ClusterRoleBinding, by label)"

  # 4. The keep-grant, only once the chart's own grant is back.
  chart_role=$(oc get roles.rbac.authorization.k8s.io -n openshift-config group-sync-dashboard-fleet-account -o json 2>/dev/null \
    | jq -r '[.rules[] | select((.resources | index("secrets")) and (.verbs | index("get")) and ((.resourceNames // []) | index("ldap-oauth-bind-secret")))] | length' 2>/dev/null || echo 0)
  chart_binding=$(oc get rolebindings.rbac.authorization.k8s.io -n openshift-config -o json 2>/dev/null \
    | jq -r --arg ns "${NS}" '[.items[] | select(.roleRef.kind == "Role" and .roleRef.name == "group-sync-dashboard-fleet-account")
         | .subjects[]? | select(.kind == "ServiceAccount" and .name == "group-sync-dashboard" and .namespace == $ns)] | length' 2>/dev/null || echo 0)
  if [ "${chart_role:-0}" -ge 1 ] && [ "${chart_binding:-0}" -ge 1 ]; then
    say "4. the chart's group-sync-dashboard-fleet-account Role and binding grant the ServiceAccount get on ldap-oauth-bind-secret: removing the keep-grant"
    say "4. $(oc delete roles.rbac.authorization.k8s.io,rolebindings.rbac.authorization.k8s.io -n openshift-config -l "${RUN_LABEL}" --ignore-not-found 2>&1 | tr '\n' ' ')"
  elif [ -n "$(oc get roles.rbac.authorization.k8s.io -n openshift-config -l "${RUN_LABEL}" -o name)" ]; then
    say "4. LEFT: the keep-grant stays — the chart's own grant on ldap-oauth-bind-secret is not back (Role rules matching: ${chart_role:-0}, bindings: ${chart_binding:-0}). Run release-crc.sh --argocd main, then this script again."
    left=1
  else
    say "4. no keep-grant present"
  fi

  # 5. developer's Lease, only once nothing configured names developer.
  if [ -n "$(oc get leases.coordination.k8s.io -n "${NS}" "${dev_lease}" -o name --ignore-not-found)" ]; then
    named=$(oc get configmaps -n "${NS}" group-sync-dashboard-config -o json | jq -r '.data["clusters.yaml"]' \
      | grep -c -E '^fleetAccountUsername: "?developer"?$|ldapConnectionBootstrap: "?developer"?$' || true)
    if [ "${named}" = 0 ]; then
      say "5. the deployed configuration names no developer account: $(oc delete leases.coordination.k8s.io -n "${NS}" "${dev_lease}" --ignore-not-found 2>&1 | tr '\n' ' ')"
    else
      say "5. LEFT: ${dev_lease} stays — the deployed configuration still names developer (${named} line(s)); a claim would re-create it. Run release-crc.sh --argocd main, then this script again."
      left=1
    fi
  else
    say "5. ${dev_lease} is absent"
  fi

  say "labelled ${RUN_LABEL} now: $(oc get secrets,roles.rbac.authorization.k8s.io,rolebindings.rbac.authorization.k8s.io -A -l "${RUN_LABEL}" -o name | tr '\n' ' ')$(oc get clusterrolebindings.rbac.authorization.k8s.io -l "${RUN_LABEL}" -o name | tr '\n' ' ')"
  say "sweep '${label}' ends: rc=${rc} left=${left}"
} 2>&1 | tee -a "${out}"
# The group ran in a pipeline's subshell: re-derive the outcome from what it wrote.
tail -1 "${out}" | grep -q 'rc=0 left=0' && exit 0
tail -1 "${out}" | grep -q 'rc=0 left=1' && exit 5
exit 1
