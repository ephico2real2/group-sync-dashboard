#!/usr/bin/env bash
# One background waiter for the walk: exits 0 when the dashboard container has logged, since <since>, at least <n>
# lines matching the extended regex <pattern>; exits 1 after <timeout> seconds. Read-only (`oc logs`), every 20 s;
# the pod is resolved on each read, so a redeploy's new pod is followed.
# Usage: wait_for_log.sh <since RFC 3339> <timeout seconds> <n> <pattern>
set -uo pipefail
since="${1:?since}"; timeout="${2:?timeout}"; n="${3:?n}"; pattern="${4:?pattern}"
ns=group-sync-dashboard
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"
deadline=$(( $(date +%s) + timeout ))
while :; do
  pod=$(oc get pods -n "${ns}" -l app.kubernetes.io/name=group-sync-dashboard \
        --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
  if [ -n "${pod}" ]; then
    got=$(oc logs -n "${ns}" "${pod}" -c dashboard --since-time="${since}" 2>/dev/null | grep -c -E -- "${pattern}")
    if [ "${got:-0}" -ge "${n}" ]; then
      echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) found ${got} line(s) matching /${pattern}/ in ${pod} since ${since}"
      exit 0
    fi
  fi
  if [ "$(date +%s)" -ge "${deadline}" ]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) TIMEOUT after ${timeout}s: ${got:-0} line(s) matching /${pattern}/ since ${since} (pod ${pod:-none})"
    exit 1
  fi
  sleep 20
done
