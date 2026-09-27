#!/usr/bin/env bash
# The lab check of SPEC_S4c §3.12 step 2 (SPEC_S4e §5), read-only: three counts of the places that could name the
# fleet account — the deployed configuration, every cluster Secret's ldapConnectionBootstrap, every onboarding
# ConfigMap. The walk places a password only after this prints `0 0 0`: before the walk Secret is created, and
# immediately before every step that places one.
#
# Usage: labcheck.sh <label>   -> evidence/<label>-labcheck.txt, and the same on stdout.
# Exit 0 only on `0 0 0`; 1 on any other count; 2 when a read failed. A failed read never counts as 0: each object
# is fetched first, and the count runs only on what came back.
set -euo pipefail
label="${1:?label}"
here="$(cd "$(dirname "$0")/.." && pwd)"   # the report folder
out="${here}/evidence/${label}-labcheck.txt"
ns=group-sync-dashboard
F=ocp-oauth-bind-serviceid
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"
fail() { echo "READ FAILED: $*" | tee -a "${out}" >&2; exit 2; }

at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
{
  echo "# SPEC_S4e §5 lab check at ${at} (read-only). The three commands, as the spec gives them:"
  echo "#   oc get configmaps -n ${ns} group-sync-dashboard-config -o json | jq -r '.data[\"clusters.yaml\"]' | grep -c \"\${F}\""
  echo "#   oc get secrets -n ${ns} -l groupsync-dashboard.io/secret-type=cluster -o json | jq --arg f \"\${F}\" '[.items[] | (.data.config // \"\" | @base64d | fromjson? // {}) | select(.ldapConnectionBootstrap == \$f)] | length'"
  echo "#   oc get configmaps -n ${ns} -l groupsync-dashboard.io/config-type -o json | jq --arg f \"\${F}\" '[.items[] | .data // {} | to_entries[] | select(.value | contains(\$f))] | length'"
  echo "# F=${F}"
} > "${out}"

cm=$(oc get configmaps -n "${ns}" group-sync-dashboard-config -o json) || fail "the deployed ConfigMap"
yaml=$(printf '%s' "${cm}" | jq -er '.data["clusters.yaml"]') || fail "clusters.yaml in the deployed ConfigMap"
c1=$(printf '%s\n' "${yaml}" | grep -c "${F}" || true)

secrets=$(oc get secrets -n "${ns}" -l groupsync-dashboard.io/secret-type=cluster -o json) || fail "the cluster Secrets"
c2=$(printf '%s' "${secrets}" \
  | jq --arg f "${F}" '[.items[] | (.data.config // "" | @base64d | fromjson? // {}) | select(.ldapConnectionBootstrap == $f)] | length') \
  || fail "counting the cluster Secrets"

cms=$(oc get configmaps -n "${ns}" -l groupsync-dashboard.io/config-type -o json) || fail "the onboarding ConfigMaps"
c3=$(printf '%s' "${cms}" \
  | jq --arg f "${F}" '[.items[] | .data // {} | to_entries[] | select(.value | contains($f))] | length') \
  || fail "counting the onboarding ConfigMaps"

# What was looked at, so a 0 is read against the objects it counts over (names and counts only).
{
  echo "# looked at: ConfigMap group-sync-dashboard-config resourceVersion $(printf '%s' "${cm}" | jq -r .metadata.resourceVersion);" \
       "fleetAccountUsername line: $(printf '%s\n' "${yaml}" | grep -E '^fleetAccountUsername:' || echo '(none)')"
  echo "# looked at: $(printf '%s' "${secrets}" | jq -r '.items | length') cluster Secret(s): $(printf '%s' "${secrets}" | jq -r '[.items[].metadata.name] | join(", ")')"
  echo "# looked at: $(printf '%s' "${cms}" | jq -r '.items | length') onboarding ConfigMap(s)"
  echo "${c1} ${c2} ${c3}"
} >> "${out}"
cat "${out}"
[ "${c1} ${c2} ${c3}" = "0 0 0" ]
