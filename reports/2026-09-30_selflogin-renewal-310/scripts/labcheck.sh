#!/usr/bin/env bash
# SPEC_S4c §3.12 step 2's lab check (SPEC_S4e §5), read-only: three counts of the places that could name the fleet
# account — the deployed configuration, every cluster Secret's ldapConnectionBootstrap, every onboarding ConfigMap.
# The walk places `developer`'s password only after this prints `0 0 0`. The commands are the spec's, with the fleet
# account's username read from its Lease into a variable (scripts/lib.sh#fleet_account) instead of written here.
#
# Usage: labcheck.sh <label>   -> evidence/<label>-labcheck.txt, and the same on stdout.
# Exit 0 only on `0 0 0`; 1 on any other counts; 2 when a read failed. A failed read never counts as 0: each object is
# fetched first, and the count runs only on what came back.
set -euo pipefail
label="${1:?label}"
# shellcheck source-path=SCRIPTDIR source=lib.sh
. "$(dirname "$0")/lib.sh"
out="${EVIDENCE}/${label}-labcheck.txt"
fail() { echo "READ FAILED: $*" | tee -a "${out}" >&2; exit 2; }

{
  echo "# SPEC_S4e §5 lab check at $(now) (read-only). F is the fleet account's username, read from its Lease; not printed."
  echo "#   oc get configmaps -n ${NS} group-sync-dashboard-config -o json | jq -r '.data[\"clusters.yaml\"]' | grep -c \"\${F}\""
  echo "#   oc get secrets -n ${NS} -l groupsync-dashboard.io/secret-type=cluster -o json | jq --arg f \"\${F}\" '[.items[] | (.data.config // \"\" | @base64d | fromjson? // {}) | select(.ldapConnectionBootstrap == \$f)] | length'"
  echo "#   oc get configmaps -n ${NS} -l groupsync-dashboard.io/config-type -o json | jq --arg f \"\${F}\" '[.items[] | .data // {} | to_entries[] | select(.value | contains(\$f))] | length'"
} > "${out}"

F=$(fleet_account) || fail "the fleet account's Lease (exactly one fleet-account Lease for an account other than developer)"

cm=$(oc get configmaps -n "${NS}" group-sync-dashboard-config -o json) || fail "the deployed ConfigMap"
yaml=$(printf '%s' "${cm}" | jq -er '.data["clusters.yaml"]') || fail "clusters.yaml in the deployed ConfigMap"
c1=$(printf '%s\n' "${yaml}" | grep -c -F -- "${F}" || true)

secrets=$(oc get secrets -n "${NS}" -l groupsync-dashboard.io/secret-type=cluster -o json) || fail "the cluster Secrets"
c2=$(printf '%s' "${secrets}" \
  | jq --arg f "${F}" '[.items[] | (.data.config // "" | @base64d | fromjson? // {}) | select(.ldapConnectionBootstrap == $f)] | length') \
  || fail "counting the cluster Secrets"

cms=$(oc get configmaps -n "${NS}" -l groupsync-dashboard.io/config-type -o json) || fail "the onboarding ConfigMaps"
c3=$(printf '%s' "${cms}" \
  | jq --arg f "${F}" '[.items[] | .data // {} | to_entries[] | select(.value | contains($f))] | length') \
  || fail "counting the onboarding ConfigMaps"

# What was looked at, so a 0 is read against the objects it counts over (names and counts only).
{
  echo "# looked at: ConfigMap group-sync-dashboard-config resourceVersion $(printf '%s' "${cm}" | jq -r .metadata.resourceVersion);" \
       "fleetAccountUsername is developer: $(printf '%s\n' "${yaml}" | grep -c -E '^fleetAccountUsername: "?developer"?$' || true);" \
       "userSelfLogin stanzas: $(printf '%s\n' "${yaml}" | grep -c -E 'userSelfLogin: true' || true)"
  echo "# looked at: $(printf '%s' "${secrets}" | jq -r '.items | length') cluster Secret(s): $(printf '%s' "${secrets}" | jq -r '[.items[].metadata.name] | join(", ")')"
  echo "# looked at: $(printf '%s' "${cms}" | jq -r '.items | length') onboarding ConfigMap(s)"
  echo "${c1} ${c2} ${c3}"
} >> "${out}"
cat "${out}"
[ "${c1} ${c2} ${c3}" = "0 0 0" ]
