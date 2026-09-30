#!/usr/bin/env bash
# oauth/cluster's session lifetime, set and settled: the ONE cluster-wide write of #310 Part A, and its restore.
#   oauth_lifetime.sh set <seconds> <label>   JSON merge patch of spec.tokenConfig.accessTokenMaxAgeSeconds alone, then
#                                             wait until the authentication operator has rolled oauth-openshift and
#                                             reports Available=True, Progressing=False, Degraded=False.
#   oauth_lifetime.sh show                    the current spec.tokenConfig.
# Idempotent, so the restore is safe to run twice: when the value is already <seconds> nothing is patched, and only the
# settled check runs. The patch names one field; spec.identityProviders and every other key are left as they are
# (scripts/baseline.sh records the sha256 of spec without tokenConfig, before and after).
# Exit 0 settled; 3 when no rollout was observed after a patch (the old lifetime may still be served); 4 when the
# rollout did not settle in time; 2 on a failed read or patch.
set -euo pipefail
# shellcheck source-path=SCRIPTDIR source=lib.sh
. "$(dirname "$0")/lib.sh"
action="${1:?set|show}"
if [ "${action}" = show ]; then token_config; exit 0; fi
[ "${action}" = set ] || { echo "usage: oauth_lifetime.sh set <seconds> <label> | show" >&2; exit 2; }
seconds="${2:?seconds}"; label="${3:?label}"
case "${seconds}" in ''|*[!0-9]*) echo "seconds must be a whole number" >&2; exit 2 ;; esac
out="${EVIDENCE}/${label}-oauth-lifetime.txt"
ROLL_TIMEOUT="${ROLL_TIMEOUT:-600}"      # for the operator to pick the change up (a new Deployment generation)
SETTLE_TIMEOUT="${SETTLE_TIMEOUT:-900}"  # for the new pod to be Ready and the operator to settle
want="{\"accessTokenMaxAgeSeconds\":${seconds}}"

state() {  # one line: the Deployment's rollout and the ClusterOperator's three conditions
  local d c
  d=$(oc get deployments.apps -n openshift-authentication oauth-openshift -o json \
      | jq -r '"generation=\(.metadata.generation) observed=\(.status.observedGeneration) replicas=\(.status.replicas // 0) updated=\(.status.updatedReplicas // 0) ready=\(.status.readyReplicas // 0) available=\(.status.availableReplicas // 0)"') || return 1
  c=$(oc get clusteroperators.config.openshift.io authentication -o json \
      | jq -r '[.status.conditions[] | select(.type | test("^(Available|Progressing|Degraded)$")) | "\(.type)=\(.status)"] | sort | join(" ")') || return 1
  printf '%s %s' "${d}" "${c}"
}
settled() {  # every replica updated and ready, nothing old left, the operator quiet
  local s="$1" g o r u rd
  g=$(sed -E 's/.*generation=([0-9]+).*/\1/' <<<"${s}"); o=$(sed -E 's/.*observed=([0-9]+).*/\1/' <<<"${s}")
  r=$(sed -E 's/.*replicas=([0-9]+).*/\1/' <<<"${s}"); u=$(sed -E 's/.*updated=([0-9]+).*/\1/' <<<"${s}")
  rd=$(sed -E 's/.*ready=([0-9]+).*/\1/' <<<"${s}")
  [ "${g}" = "${o}" ] && [ "${r}" = "${u}" ] && [ "${u}" = "${rd}" ] && [ "${rd}" -ge 1 ] \
    && grep -q 'Available=True Degraded=False Progressing=False' <<<"${s}"
}
generation() { oc get deployments.apps -n openshift-authentication oauth-openshift -o jsonpath='{.metadata.generation}'; }

{
  say "want spec.tokenConfig ${want}"
  cur=$(token_config) || { say "READ FAILED: oauth/cluster"; exit 2; }
  say "found spec.tokenConfig ${cur}; $(state)"
  if [ "${cur}" = "${want}" ]; then
    say "already ${seconds}: nothing patched; checking that the operator is settled"
  else
    gen0=$(generation)
    say "oc patch oauths.config.openshift.io cluster --type=merge -p '{\"spec\":{\"tokenConfig\":{\"accessTokenMaxAgeSeconds\":${seconds}}}}'"
    oc patch oauths.config.openshift.io cluster --type=merge \
      -p "{\"spec\":{\"tokenConfig\":{\"accessTokenMaxAgeSeconds\":${seconds}}}}" || { say "PATCH FAILED"; exit 2; }
    after=$(token_config)
    say "spec.tokenConfig now ${after}"
    [ "${after}" = "${want}" ] || { say "UNEXPECTED: spec.tokenConfig is ${after}, not ${want}"; exit 2; }
    deadline=$(( $(date +%s) + ROLL_TIMEOUT ))
    until [ "$(generation)" -gt "${gen0}" ]; do
      if [ "$(date +%s)" -ge "${deadline}" ]; then
        say "NO ROLLOUT OBSERVED in ${ROLL_TIMEOUT}s: oauth-openshift is still at generation ${gen0}; the served lifetime is unknown"
        exit 3
      fi
      sleep 10
    done
    say "the operator rolled oauth-openshift: generation ${gen0} -> $(generation)"
  fi
  deadline=$(( $(date +%s) + SETTLE_TIMEOUT )); last=""
  while :; do
    s=$(state || echo "state unreadable")
    [ "${s}" != "${last}" ] && say "${s}"; last="${s}"
    if settled "${s}"; then say "SETTLED"; break; fi
    if [ "$(date +%s)" -ge "${deadline}" ]; then say "NOT SETTLED in ${SETTLE_TIMEOUT}s"; exit 4; fi
    sleep 10
  done
  oc get pods -n openshift-authentication -l app=oauth-openshift -o json \
    | jq -r '.items[] | "pod \(.metadata.name) phase=\(.status.phase) started=\(.status.startTime)"'
} 2>&1 | tee -a "${out}"
exit "${PIPESTATUS[0]}"
